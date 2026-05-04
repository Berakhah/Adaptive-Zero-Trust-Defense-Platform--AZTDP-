package com.aztdp.springapp.client;

public class RiskClientException extends RuntimeException {
    private final String code;

    public RiskClientException(String code) {
        super(code);
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
