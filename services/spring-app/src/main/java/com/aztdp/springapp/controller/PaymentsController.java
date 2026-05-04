package com.aztdp.springapp.controller;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentsController {
    @GetMapping("/v1/payments/{paymentId}")
    public Map<String, String> paymentDetail(@PathVariable String paymentId) {
        return Map.of("payment_id", paymentId);
    }
}
