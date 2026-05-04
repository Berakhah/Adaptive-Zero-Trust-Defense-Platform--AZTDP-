package com.aztdp.springapp.security;

import jakarta.servlet.http.HttpServletRequest;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Resolves real client IP / geo under a trusted reverse-proxy chain.
 *
 * <p>X-Client-Ip, X-Forwarded-For and X-Geo headers are honored only when the
 * immediate connection (request.getRemoteAddr()) is inside a trusted CIDR.
 * Otherwise the headers are ignored and getRemoteAddr() wins. This closes the
 * spoofing surface where any HTTP client could set X-Client-Ip to bypass the
 * IP/geo drift signals.
 */
public final class ClientIpResolver {

    private final List<Cidr> trusted;

    public ClientIpResolver(String csvCidrs) {
        this.trusted = parse(csvCidrs);
    }

    public String resolveIp(HttpServletRequest request) {
        String remote = safe(request.getRemoteAddr());
        if (!isTrusted(remote)) {
            return remote;
        }
        String xClientIp = safe(request.getHeader("X-Client-Ip"));
        if (!xClientIp.isEmpty()) {
            return xClientIp;
        }
        String xff = safe(request.getHeader("X-Forwarded-For"));
        if (!xff.isEmpty()) {
            int comma = xff.indexOf(',');
            return (comma > 0 ? xff.substring(0, comma) : xff).trim();
        }
        return remote;
    }

    public String resolveGeo(HttpServletRequest request) {
        if (!isTrusted(safe(request.getRemoteAddr()))) {
            return "";
        }
        return safe(request.getHeader("X-Geo"));
    }

    private boolean isTrusted(String ip) {
        if (ip.isEmpty() || trusted.isEmpty()) {
            return false;
        }
        try {
            byte[] addr = InetAddress.getByName(ip).getAddress();
            for (Cidr c : trusted) {
                if (c.contains(addr)) return true;
            }
        } catch (UnknownHostException ignored) {
        }
        return false;
    }

    private static String safe(String v) {
        return v == null ? "" : v.trim();
    }

    private static List<Cidr> parse(String csv) {
        List<Cidr> out = new ArrayList<>();
        if (csv == null || csv.isBlank()) return out;
        for (String chunk : csv.split(",")) {
            chunk = chunk.trim();
            if (chunk.isEmpty()) continue;
            try {
                out.add(Cidr.of(chunk));
            } catch (Exception ignored) {
            }
        }
        return out;
    }

    private static final class Cidr {
        private final byte[] network;
        private final int prefixLen;

        private Cidr(byte[] network, int prefixLen) {
            this.network = network;
            this.prefixLen = prefixLen;
        }

        static Cidr of(String spec) throws UnknownHostException {
            int slash = spec.indexOf('/');
            String host = slash < 0 ? spec : spec.substring(0, slash);
            byte[] addr = InetAddress.getByName(host).getAddress();
            int prefix = slash < 0 ? addr.length * 8 : Integer.parseInt(spec.substring(slash + 1));
            return new Cidr(applyMask(addr, prefix), prefix);
        }

        boolean contains(byte[] addr) {
            if (addr.length != network.length) return false;
            byte[] masked = applyMask(addr, prefixLen);
            return Arrays.equals(masked, network);
        }

        private static byte[] applyMask(byte[] addr, int prefix) {
            byte[] out = addr.clone();
            int fullBytes = prefix / 8;
            int bits = prefix % 8;
            for (int i = fullBytes; i < out.length; i++) {
                out[i] = 0;
            }
            if (bits > 0 && fullBytes < out.length) {
                int mask = 0xFF << (8 - bits) & 0xFF;
                out[fullBytes] = (byte) (addr[fullBytes] & mask);
            }
            return out;
        }
    }
}
