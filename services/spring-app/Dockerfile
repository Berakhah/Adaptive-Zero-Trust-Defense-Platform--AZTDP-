FROM eclipse-temurin:25-jdk-alpine@sha256:3fd2d245c4e0eba615fe366a71b8bd25f5db7104f53e4026b24bf508b880bd2a AS build
WORKDIR /build
RUN apk add --no-cache maven
COPY pom.xml .
RUN mvn dependency:go-offline -q
COPY src ./src
# Tests run in CI (mvn verify); the image build skips them.
RUN mvn package -Dmaven.test.skip=true -q

FROM eclipse-temurin:25-jre-alpine@sha256:3c0a9084927a221ccd1d007fcaf614465672c0af37aaa834c5184483afe56d61
WORKDIR /app
RUN adduser -S -D -H -u 10001 app
COPY --from=build --chown=app /build/target/spring-app-*.jar app.jar
USER 10001:10001
EXPOSE 8082
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=5 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8082/actuator/health"]
CMD ["java", "-jar", "app.jar"]
