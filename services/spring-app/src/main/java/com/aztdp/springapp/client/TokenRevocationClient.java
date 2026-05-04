package com.aztdp.springapp.client;

import com.aztdp.springapp.config.AztdpProperties;
import java.util.Map;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class TokenRevocationClient {
    private final RestTemplate restTemplate;
    private final AztdpProperties properties;

    public TokenRevocationClient(RestTemplate restTemplate, AztdpProperties properties) {
        this.restTemplate = restTemplate;
        this.properties = properties;
    }

    public void revoke(String tokenJtiHash, String reason) {
        String url = properties.getTokenRevocationUrl();
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Token", properties.getInternalToken());
        restTemplate.postForObject(
            url,
            new HttpEntity<>(Map.of("token_jti_hash", tokenJtiHash, "reason", reason, "source", "policy"), headers),
            Map.class
        );
    }
}
