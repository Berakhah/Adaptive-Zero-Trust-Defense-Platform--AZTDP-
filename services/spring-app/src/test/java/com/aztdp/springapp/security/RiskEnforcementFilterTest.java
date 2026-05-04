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
import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RiskEnforcementFilterTest {

    private RiskClient riskClient;
    private PolicyClient policyClient;
    private TokenRevocationClient revocationClient;
    private AztdpProperties properties;
    private RiskEnforcementFilter filter;
    private FilterChain chain;

    @BeforeEach
    void setUp() {
        riskClient = mock(RiskClient.class);
        policyClient = mock(PolicyClient.class);
        revocationClient = mock(TokenRevocationClient.class);
        properties = new AztdpProperties();
        filter = new RiskEnforcementFilter(riskClient, policyClient, revocationClient, properties);
        chain = mock(FilterChain.class);
        SecurityContextHolder.clearContext();
    }

    @Test
    void healthPathBypassesFilter() {
        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/health");
        assertThat(filter.shouldNotFilter(req)).isTrue();
    }

    @Test
    void replayDetectedReturns403EvenWhenFailOpen() throws Exception {
        properties.setFailOpen(true);
        MockHttpServletRequest req = authenticatedRequest("/v1/payments/1");
        MockHttpServletResponse res = new MockHttpServletResponse();
        when(riskClient.evaluate(any(RiskRequest.class)))
            .thenThrow(new RiskClientException("replay_detected"));

        filter.doFilter(req, res, chain);

        assertThat(res.getStatus()).isEqualTo(403);
        verify(chain, never()).doFilter(any(), any());
    }

    @Test
    void riskUnavailableFailsClosedByDefault() throws Exception {
        MockHttpServletRequest req = authenticatedRequest("/v1/payments/1");
        MockHttpServletResponse res = new MockHttpServletResponse();
        when(riskClient.evaluate(any(RiskRequest.class)))
            .thenThrow(new RiskClientException("risk_unavailable"));

        filter.doFilter(req, res, chain);

        assertThat(res.getStatus()).isEqualTo(403);
    }

    @Test
    void allowDecisionInvokesNextFilter() throws Exception {
        MockHttpServletRequest req = authenticatedRequest("/v1/payments/1");
        MockHttpServletResponse res = new MockHttpServletResponse();
        when(riskClient.evaluate(any(RiskRequest.class))).thenReturn(new RiskResponse());
        PolicyDecision decision = new PolicyDecision();
        decision.setDecision("allow");
        when(policyClient.decide(any(PolicyInput.class))).thenReturn(decision);

        filter.doFilter(req, res, chain);

        verify(chain).doFilter(req, res);
    }

    @Test
    void denyDecisionReturns403() throws Exception {
        MockHttpServletRequest req = authenticatedRequest("/v1/payments/1");
        MockHttpServletResponse res = new MockHttpServletResponse();
        when(riskClient.evaluate(any(RiskRequest.class))).thenReturn(new RiskResponse());
        PolicyDecision decision = new PolicyDecision();
        decision.setDecision("deny");
        decision.setReason(Map.of("rule", "high_risk"));
        when(policyClient.decide(any(PolicyInput.class))).thenReturn(decision);

        filter.doFilter(req, res, chain);

        assertThat(res.getStatus()).isEqualTo(403);
    }

    private MockHttpServletRequest authenticatedRequest(String path) {
        MockHttpServletRequest req = new MockHttpServletRequest("GET", path);
        req.addHeader("X-Client-Ip", "1.1.1.1");
        req.addHeader("User-Agent", "test-ua");
        req.addHeader("X-Geo", "US-CA");
        Jwt jwt = Jwt.withTokenValue("token")
            .header("alg", "RS256")
            .issuedAt(Instant.now())
            .expiresAt(Instant.now().plusSeconds(300))
            .claim("sub", "user-1")
            .claim("jti", "jti-1")
            .claim("realm_access", Map.of("roles", List.of("user")))
            .build();
        JwtAuthenticationToken auth = new JwtAuthenticationToken(jwt);
        req.setUserPrincipal(auth);
        return req;
    }
}
