package com.aztdp.springapp.client;

import com.aztdp.springapp.config.AztdpProperties;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

@Component
public class TokenRevocationClient {
    private final RestTemplate restTemplate;
    private final AztdpProperties properties;

    public TokenRevocationClient(RestTemplate restTemplate, AztdpProperties properties) {
        this.restTemplate = restTemplate;
        this.properties = properties;
    }

    /**
     * Revoke a token at the gateway.
     *
     * @param expiresAt the access token's {@code exp}; bounds the gateway's cache TTL. May be null.
     * @throws TokenRevocationException if the gateway did not durably record the revocation
     */
    public void revoke(String tokenJtiHash, String reason, Instant expiresAt) {
        String url = properties.getTokenRevocationUrl();
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Token", properties.getInternalToken());
        Map<String, Object> body = new HashMap<>();
        body.put("token_jti_hash", tokenJtiHash);
        body.put("reason", reason);
        body.put("source", "policy");
        if (expiresAt != null) {
            body.put("expires_at", expiresAt.getEpochSecond());
        }
        try {
            restTemplate.postForObject(url, new HttpEntity<>(body, headers), Map.class);
        } catch (HttpStatusCodeException exc) {
            if (exc.getStatusCode().value() == 503) {
                throw new TokenRevocationException("revocation_not_persisted", exc);
            }
            throw new TokenRevocationException("revocation_unavailable", exc);
        } catch (RestClientException exc) {
            throw new TokenRevocationException("revocation_unavailable", exc);
        }
    }
}
