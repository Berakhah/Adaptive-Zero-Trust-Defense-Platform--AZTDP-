package com.aztdp.springapp.client;

import com.aztdp.springapp.config.AztdpProperties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

import java.time.Instant;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class TokenRevocationClientTest {

    private RestTemplate restTemplate;
    private TokenRevocationClient client;

    @BeforeEach
    void setUp() {
        restTemplate = mock(RestTemplate.class);
        AztdpProperties properties = new AztdpProperties();
        properties.setTokenRevocationUrl("http://gateway:8080/v1/tokens/revoke");
        properties.setInternalToken("internal");
        client = new TokenRevocationClient(restTemplate, properties);
    }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void sendsTokenExpAsExpiresAtEpochSeconds() {
        client.revoke("hash-1", "policy", Instant.ofEpochSecond(1_760_000_123L));

        ArgumentCaptor<HttpEntity> captor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).postForObject(
            eq("http://gateway:8080/v1/tokens/revoke"), captor.capture(), eq(Map.class));
        Map<String, Object> body = (Map<String, Object>) captor.getValue().getBody();
        assertThat(body).containsEntry("token_jti_hash", "hash-1")
            .containsEntry("source", "policy")
            .containsEntry("expires_at", 1_760_000_123L);
        assertThat(captor.getValue().getHeaders().getFirst("X-Internal-Token")).isEqualTo("internal");
    }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void omitsExpiresAtWhenTokenHasNoExp() {
        client.revoke("hash-1", "policy", null);

        ArgumentCaptor<HttpEntity> captor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).postForObject(any(String.class), captor.capture(), eq(Map.class));
        Map<String, Object> body = (Map<String, Object>) captor.getValue().getBody();
        assertThat(body).doesNotContainKey("expires_at");
    }

    @Test
    void translates503ToRevocationNotPersisted() {
        when(restTemplate.postForObject(any(String.class), any(), eq(Map.class)))
            .thenThrow(HttpServerErrorException.create(
                HttpStatus.SERVICE_UNAVAILABLE, "unavailable", null, null, null));

        assertThatThrownBy(() -> client.revoke("hash-1", "policy", null))
            .isInstanceOf(TokenRevocationException.class)
            .hasMessage("revocation_not_persisted");
    }

    @Test
    void translatesNetworkFailureToRevocationUnavailable() {
        when(restTemplate.postForObject(any(String.class), any(), eq(Map.class)))
            .thenThrow(new ResourceAccessException("connection refused"));

        assertThatThrownBy(() -> client.revoke("hash-1", "policy", null))
            .isInstanceOf(TokenRevocationException.class)
            .hasMessage("revocation_unavailable");
    }
}
