package com.aztdp.springapp.model;

import java.time.Instant;

public class RiskRequest {
    private String requestId;
    private String sessionId;
    private String userId;
    private String tokenJtiHash;
    private String ip;
    private String geo;
    private String userAgentHash;
    private Endpoint endpoint;
    private String timestamp;

    public static RiskRequest from(
            String requestId,
            String sessionId,
            String userId,
            String tokenJtiHash,
            String ip,
            String geo,
            String userAgentHash,
            String method,
            String path,
            int sensitivity
    ) {
        RiskRequest request = new RiskRequest();
        request.requestId = requestId;
        request.sessionId = sessionId;
        request.userId = userId;
        request.tokenJtiHash = tokenJtiHash;
        request.ip = ip;
        request.geo = geo;
        request.userAgentHash = userAgentHash;
        request.endpoint = new Endpoint("spring-app", method, path, sensitivity);
        request.timestamp = Instant.now().toString();
        return request;
    }

    public String getRequestId() {
        return requestId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public String getUserId() {
        return userId;
    }

    public String getTokenJtiHash() {
        return tokenJtiHash;
    }

    public String getIp() {
        return ip;
    }

    public String getGeo() {
        return geo;
    }

    public String getUserAgentHash() {
        return userAgentHash;
    }

    public Endpoint getEndpoint() {
        return endpoint;
    }

    public String getTimestamp() {
        return timestamp;
    }

    public static class Endpoint {
        private String service;
        private String method;
        private String path;
        private int sensitivity;

        public Endpoint() {}

        public Endpoint(String service, String method, String path, int sensitivity) {
            this.service = service;
            this.method = method;
            this.path = path;
            this.sensitivity = sensitivity;
        }

        public String getService() {
            return service;
        }

        public String getMethod() {
            return method;
        }

        public String getPath() {
            return path;
        }

        public int getSensitivity() {
            return sensitivity;
        }
    }
}
