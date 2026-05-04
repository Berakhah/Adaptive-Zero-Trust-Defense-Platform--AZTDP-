package com.aztdp.springapp.client;

import com.aztdp.springapp.config.AztdpProperties;
import com.aztdp.springapp.model.RiskRequest;
import com.aztdp.springapp.model.RiskResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class RiskClientTest {

    private RestTemplate restTemplate;
    private AztdpProperties properties;
    private RiskClient client;

    @BeforeEach
    void setUp() {
        restTemplate = mock(RestTemplate.class);
        properties = new AztdpProperties();
        properties.setRiskEngineUrl("http://risk-engine:8080");
        client = new RiskClient(restTemplate, properties);
    }

    @Test
    void returnsResponseOnSuccess() {
        RiskResponse response = new RiskResponse();
        response.setRiskScore(0.1);
        response.setTrustScore(0.9);
        when(restTemplate.postForObject(eq("http://risk-engine:8080/v1/risk/evaluate"), any(), eq(RiskResponse.class)))
            .thenReturn(response);

        RiskResponse out = client.evaluate(sampleRequest());
        assertThat(out.getRiskScore()).isEqualTo(0.1);
    }

    @Test
    void translates409ToReplayDetected() {
        when(restTemplate.postForObject(any(String.class), any(), eq(RiskResponse.class)))
            .thenThrow(HttpClientErrorException.create(HttpStatus.CONFLICT, "conflict", null, null, null));

        assertThatThrownBy(() -> client.evaluate(sampleRequest()))
            .isInstanceOf(RiskClientException.class)
            .hasMessage("replay_detected");
    }

    @Test
    void translatesGenericFailureToRiskUnavailable() {
        when(restTemplate.postForObject(any(String.class), any(), eq(RiskResponse.class)))
            .thenThrow(new RestClientException("network down"));

        assertThatThrownBy(() -> client.evaluate(sampleRequest()))
            .isInstanceOf(RiskClientException.class)
            .hasMessage("risk_unavailable");
    }

    @Test
    void nullResponseIsTreatedAsUnavailable() {
        when(restTemplate.postForObject(any(String.class), any(), eq(RiskResponse.class)))
            .thenReturn(null);

        assertThatThrownBy(() -> client.evaluate(sampleRequest()))
            .isInstanceOf(RiskClientException.class)
            .hasMessage("risk_unavailable");
    }

    private RiskRequest sampleRequest() {
        return RiskRequest.from(
            "req-1", "sess-1", "user-1", "hash-1",
            "1.1.1.1", "US-CA", "ua-1",
            "GET", "/v1/payments/1", 4
        );
    }
}
