package com.aztdp.springapp.client;

import com.aztdp.springapp.config.AztdpProperties;
import com.aztdp.springapp.model.RiskRequest;
import com.aztdp.springapp.model.RiskResponse;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

@Component
public class RiskClient {
    private final RestTemplate restTemplate;
    private final AztdpProperties properties;

    public RiskClient(RestTemplate restTemplate, AztdpProperties properties) {
        this.restTemplate = restTemplate;
        this.properties = properties;
    }

    public RiskResponse evaluate(RiskRequest request) {
        String url = properties.getRiskEngineUrl() + "/v1/risk/evaluate";
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.set("X-Internal-Token", properties.getInternalToken());
            RiskResponse response = restTemplate.postForObject(url, new HttpEntity<>(request, headers), RiskResponse.class);
            if (response == null) {
                throw new RiskClientException("risk_unavailable");
            }
            return response;
        } catch (HttpClientErrorException exc) {
            if (exc.getStatusCode() == HttpStatus.CONFLICT) {
                throw new RiskClientException("replay_detected");
            }
            throw new RiskClientException("risk_unavailable");
        } catch (RestClientException exc) {
            throw new RiskClientException("risk_unavailable");
        }
    }
}
