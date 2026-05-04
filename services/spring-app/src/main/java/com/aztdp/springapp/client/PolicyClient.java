package com.aztdp.springapp.client;

import com.aztdp.springapp.config.AztdpProperties;
import com.aztdp.springapp.model.PolicyDecision;
import com.aztdp.springapp.model.PolicyInput;
import java.util.Map;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class PolicyClient {
    private final RestTemplate restTemplate;
    private final AztdpProperties properties;

    public PolicyClient(RestTemplate restTemplate, AztdpProperties properties) {
        this.restTemplate = restTemplate;
        this.properties = properties;
    }

    @SuppressWarnings("unchecked")
    public PolicyDecision decide(PolicyInput input) {
        String url = properties.getPolicyGatewayUrl() + "/v1/policy/decision";
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Token", properties.getInternalToken());
        Map<String, Object> response = restTemplate.postForObject(url, new HttpEntity<>(input, headers), Map.class);
        if (response == null) {
            return PolicyDecision.deny("empty_response");
        }
        Object decisionObj = response.get("decision");
        if (decisionObj instanceof Map<?, ?> map) {
            return PolicyDecision.fromMap((Map<String, Object>) map);
        }
        Object resultObj = response.get("result");
        if (resultObj instanceof Map<?, ?> map) {
            return PolicyDecision.fromMap((Map<String, Object>) map);
        }
        return PolicyDecision.deny("invalid_response");
    }
}
