package com.aztdp.springapp.model;

import java.util.List;
import java.util.Map;

public class RiskResponse {
    private double riskScore;
    private double trustScore;
    private List<Map<String, Object>> reasons;
    private double anomalyScore;

    public double getRiskScore() {
        return riskScore;
    }

    public void setRiskScore(double riskScore) {
        this.riskScore = riskScore;
    }

    public double getTrustScore() {
        return trustScore;
    }

    public void setTrustScore(double trustScore) {
        this.trustScore = trustScore;
    }

    public List<Map<String, Object>> getReasons() {
        return reasons;
    }

    public void setReasons(List<Map<String, Object>> reasons) {
        this.reasons = reasons;
    }

    public double getAnomalyScore() {
        return anomalyScore;
    }

    public void setAnomalyScore(double anomalyScore) {
        this.anomalyScore = anomalyScore;
    }
}
