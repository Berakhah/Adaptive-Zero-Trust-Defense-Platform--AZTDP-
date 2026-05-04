package com.aztdp.springapp.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "aztdp")
public class AztdpProperties {
    private String riskEngineUrl;
    private String policyGatewayUrl;
    private String tokenRevocationUrl;
    private String trustedProxies = "";
    private boolean failOpen;
    private String internalToken = "";
    private Timeouts timeouts = new Timeouts();

    public String getTrustedProxies() {
        return trustedProxies;
    }

    public void setTrustedProxies(String trustedProxies) {
        this.trustedProxies = trustedProxies == null ? "" : trustedProxies;
    }

    public String getRiskEngineUrl() {
        return riskEngineUrl;
    }

    public void setRiskEngineUrl(String riskEngineUrl) {
        this.riskEngineUrl = riskEngineUrl;
    }

    public String getPolicyGatewayUrl() {
        return policyGatewayUrl;
    }

    public void setPolicyGatewayUrl(String policyGatewayUrl) {
        this.policyGatewayUrl = policyGatewayUrl;
    }

    public String getTokenRevocationUrl() {
        return tokenRevocationUrl;
    }

    public void setTokenRevocationUrl(String tokenRevocationUrl) {
        this.tokenRevocationUrl = tokenRevocationUrl;
    }

    public boolean isFailOpen() {
        return failOpen;
    }

    public void setFailOpen(boolean failOpen) {
        this.failOpen = failOpen;
    }

    public String getInternalToken() {
        return internalToken;
    }

    public void setInternalToken(String internalToken) {
        this.internalToken = internalToken == null ? "" : internalToken;
    }

    public Timeouts getTimeouts() {
        return timeouts;
    }

    public void setTimeouts(Timeouts timeouts) {
        this.timeouts = timeouts;
    }

    public static class Timeouts {
        private int connectMs = 200;
        private int readMs = 800;

        public int getConnectMs() {
            return connectMs;
        }

        public void setConnectMs(int connectMs) {
            this.connectMs = connectMs;
        }

        public int getReadMs() {
            return readMs;
        }

        public void setReadMs(int readMs) {
            this.readMs = readMs;
        }
    }
}
