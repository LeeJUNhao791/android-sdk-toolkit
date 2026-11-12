package io.github.leejunhao791.sdktoolkit.consumer;

import io.github.leejunhao791.sdktoolkit.javademo.JavaDeviceSdk;
import io.github.leejunhao791.sdktoolkit.javademo.Reading;

public final class Smoke {
    public static void main(String[] args) {
        Reading reading = JavaDeviceSdk.read(42);
        if (reading.value() != 42) {
            throw new AssertionError("Unexpected SDK result");
        }
        System.out.println("Java SDK and transitive dependency returned 42");
    }
}
