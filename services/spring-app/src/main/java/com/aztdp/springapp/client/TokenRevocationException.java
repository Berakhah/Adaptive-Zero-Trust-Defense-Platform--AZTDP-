package com.aztdp.springapp.client;

/**
 * A revocation call failed. The message is the code: {@code revocation_not_persisted}
 * (gateway answered 503) or {@code revocation_unavailable} (network / other error).
 */
public class TokenRevocationException extends RuntimeException {
    private final String code;

    public TokenRevocationException(String code, Throwable cause) {
        super(code, cause);
        this.code = code;
    }

    public TokenRevocationException(String code) {
        this(code, null);
    }

    public String getCode() {
        return code;
    }
}
