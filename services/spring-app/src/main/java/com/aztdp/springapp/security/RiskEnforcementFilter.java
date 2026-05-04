package com.aztdp.springapp.security;

import com.aztdp.springapp.client.PolicyClient;
import com.aztdp.springapp.client.RiskClient;
import com.aztdp.springapp.client.RiskClientException;
import com.aztdp.springapp.client.TokenRevocationClient;
import com.aztdp.springapp.config.AztdpProperties;
import com.aztdp.springapp.model.PolicyDecision;
import com.aztdp.springapp.model.PolicyInput;
import com.aztdp.springapp.model.RiskRequest;
import com.aztdp.springapp.model.RiskResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RiskEnforcementFilter extends OncePerRequestFilter {
    private final RiskClient riskClient;
    private final PolicyClient policyClient;
    private final TokenRevocationClient revocationClient;
    private final AztdpProperties properties;
    private final ClientIpResolver clientIpResolver;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public RiskEnforcementFilter(
            RiskClient riskClient,
            PolicyClient policyClient,
            TokenRevocationClient revocationClient,
            AztdpProperties properties
    ) {
        this.riskClient = riskClient;
        this.policyClient = policyClient;
        this.revocationClient = revocationClient;
        this.properties = properties;
        this.clientIpResolver = new ClientIpResolver(properties.getTrustedProxies());
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return path.startsWith("/health") || path.startsWith("/metrics") || path.startsWith("/actuator");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        Authentication authentication = (Authentication) request.getUserPrincipal();
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            writeError(response, HttpStatus.UNAUTHORIZED, "missing_token");
            return;
        }

        String requestId = headerOrDefault(request, "X-Request-Id", UUID.randomUUID().toString());
        String sessionId = claimOrEmpty(jwtAuth, "sid");
        String subjectId = claimOrEmpty(jwtAuth, "sub");
        String jti = claimOrEmpty(jwtAuth, "jti");
        String tokenHash = jti.isEmpty() ? "" : sha256(jti);
        String uaHash = sha256(headerOrDefault(request, "User-Agent", ""));
        String clientIp = clientIpResolver.resolveIp(request);
        String geo = clientIpResolver.resolveGeo(request);
        int sensitivity = endpointSensitivity(request.getRequestURI(), request.getMethod());

        RiskRequest riskRequest = RiskRequest.from(
            requestId,
            sessionId,
            subjectId,
            tokenHash,
            clientIp,
            geo,
            uaHash,
            request.getMethod(),
            request.getRequestURI(),
            sensitivity
        );

        RiskResponse riskResponse;
        try {
            riskResponse = riskClient.evaluate(riskRequest);
        } catch (RiskClientException exc) {
            if ("replay_detected".equals(exc.getCode())) {
                writeError(response, HttpStatus.FORBIDDEN, "token_replay");
                return;
            }
            if (properties.isFailOpen()) {
                filterChain.doFilter(request, response);
                return;
            }
            writeError(response, HttpStatus.FORBIDDEN, "risk_unavailable");
            return;
        }

        PolicyInput policyInput = PolicyInput.from(
            requestId,
            subjectId,
            tokenHash,
            roles(jwtAuth),
            request.getMethod(),
            request.getRequestURI(),
            sensitivity,
            clientIp,
            geo,
            riskResponse
        );

        PolicyDecision decision;
        try {
            decision = policyClient.decide(policyInput);
        } catch (Exception exc) {
            if (properties.isFailOpen()) {
                filterChain.doFilter(request, response);
                return;
            }
            writeError(response, HttpStatus.FORBIDDEN, "policy_unavailable");
            return;
        }

        String action = decision.getDecision();
        if ("allow".equalsIgnoreCase(action)) {
            filterChain.doFilter(request, response);
            return;
        }
        if ("stepup".equalsIgnoreCase(action)) {
            writeStepUp(response, decision);
            return;
        }
        if ("revoke".equalsIgnoreCase(action)) {
            if (!tokenHash.isEmpty()) {
                revocationClient.revoke(tokenHash, "policy");
            }
            writeError(response, HttpStatus.FORBIDDEN, "token_revoked");
            return;
        }

        writeError(response, HttpStatus.FORBIDDEN, "policy_denied");
    }

    private List<String> roles(JwtAuthenticationToken jwtAuth) {
        Object realmAccess = jwtAuth.getTokenAttributes().get("realm_access");
        if (realmAccess instanceof Map<?, ?> map && map.get("roles") instanceof List<?> list) {
            return list.stream().map(Object::toString).toList();
        }
        return List.of();
    }

    private int endpointSensitivity(String path, String method) {
        if (path.startsWith("/v1/payments")) {
            return 4;
        }
        if (path.startsWith("/v1/admin")) {
            return 5;
        }
        if ("POST".equalsIgnoreCase(method)) {
            return 3;
        }
        return 2;
    }

    private String claimOrEmpty(JwtAuthenticationToken jwtAuth, String claim) {
        Object value = jwtAuth.getTokenAttributes().get(claim);
        return value == null ? "" : value.toString();
    }

    private String headerOrDefault(HttpServletRequest request, String header, String fallback) {
        String value = request.getHeader(header);
        return value == null ? fallback : value;
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hashed = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder();
            for (byte b : hashed) {
                builder.append(String.format("%02x", b));
            }
            return builder.toString();
        } catch (Exception exc) {
            return "";
        }
    }

    private void writeError(HttpServletResponse response, HttpStatus status, String code)
            throws IOException {
        response.setStatus(status.value());
        response.setContentType("application/json");
        response.getWriter().write(
            objectMapper.writeValueAsString(
                Map.of("error", Map.of("code", code, "timestamp", Instant.now().toString()))
            )
        );
    }

    private void writeStepUp(HttpServletResponse response, PolicyDecision decision) throws IOException {
        response.setStatus(HttpStatus.UNAUTHORIZED.value());
        response.setContentType("application/json");
        String challengeId = decision.getReason().getOrDefault("challenge_id", UUID.randomUUID().toString());
        response.getWriter().write(
            objectMapper.writeValueAsString(
                Map.of(
                    "error",
                    Map.of(
                        "code", "STEP_UP_REQUIRED",
                        "message", "Additional authentication required",
                        "details",
                        Map.of(
                            "challenge_id", challengeId,
                            "methods", List.of("otp", "webauthn"),
                            "expires_in_seconds", 300
                        )
                    )
                )
            )
        );
    }
}
