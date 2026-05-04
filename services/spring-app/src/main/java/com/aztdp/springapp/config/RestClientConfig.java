package com.aztdp.springapp.config;

import java.util.List;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration
@EnableConfigurationProperties(AztdpProperties.class)
public class RestClientConfig {
    @Bean
    public RestTemplate restTemplate(AztdpProperties properties) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(properties.getTimeouts().getConnectMs());
        factory.setReadTimeout(properties.getTimeouts().getReadMs());
        RestTemplate template = new RestTemplate(factory);

        String token = properties.getInternalToken();
        if (token != null && !token.isEmpty()) {
            ClientHttpRequestInterceptor interceptor = (request, body, execution) -> {
                request.getHeaders().set("X-Internal-Token", token);
                return execution.execute(request, body);
            };
            template.setInterceptors(List.of(interceptor));
        }

        return template;
    }
}
