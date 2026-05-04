package com.aztdp.springapp.model;

import java.util.List;

public class PolicyInput {
    private Input input;

    public static PolicyInput from(
            String requestId,
            String subjectId,
            String tokenJtiHash,
            List<String> roles,
            String method,
            String path,
            int sensitivity,
            String ip,
            String geo,
            RiskResponse risk
    ) {
        PolicyInput policyInput = new PolicyInput();
        Input input = new Input();
        input.requestId = requestId;
        input.subject = new Subject(subjectId, roles, risk.getTrustScore());
        input.resource = new Resource("spring-app", method, path, sensitivity);
        input.context = new Context(risk.getRiskScore(), ip, geo, tokenJtiHash, false, risk.getAnomalyScore());
        policyInput.input = input;
        return policyInput;
    }

    public Input getInput() {
        return input;
    }

    public static class Input {
        private String requestId;
        private Subject subject;
        private Resource resource;
        private Context context;

        public String getRequestId() {
            return requestId;
        }

        public Subject getSubject() {
            return subject;
        }

        public Resource getResource() {
            return resource;
        }

        public Context getContext() {
            return context;
        }
    }

    public static class Subject {
        private String userId;
        private List<String> roles;
        private double sessionTrust;

        public Subject() {}

        public Subject(String userId, List<String> roles, double sessionTrust) {
            this.userId = userId;
            this.roles = roles;
            this.sessionTrust = sessionTrust;
        }

        public String getUserId() {
            return userId;
        }

        public List<String> getRoles() {
            return roles;
        }

        public double getSessionTrust() {
            return sessionTrust;
        }
    }

    public static class Resource {
        private String service;
        private String method;
        private String path;
        private int sensitivity;

        public Resource() {}

        public Resource(String service, String method, String path, int sensitivity) {
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

    public static class Context {
        private double riskScore;
        private String ip;
        private String geo;
        private String tokenJtiHash;
        private boolean isTokenRevoked;
        private double anomalyScore;

        public Context() {}

        public Context(
                double riskScore,
                String ip,
                String geo,
                String tokenJtiHash,
                boolean isTokenRevoked,
                double anomalyScore
        ) {
            this.riskScore = riskScore;
            this.ip = ip;
            this.geo = geo;
            this.tokenJtiHash = tokenJtiHash;
            this.isTokenRevoked = isTokenRevoked;
            this.anomalyScore = anomalyScore;
        }

        public double getRiskScore() {
            return riskScore;
        }

        public String getIp() {
            return ip;
        }

        public String getGeo() {
            return geo;
        }

        public String getTokenJtiHash() {
            return tokenJtiHash;
        }

        public boolean isTokenRevoked() {
            return isTokenRevoked;
        }

        public double getAnomalyScore() {
            return anomalyScore;
        }
    }
}
