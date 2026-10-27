FROM eclipse-temurin:25-jdk-alpine@sha256:1e20ead9eec7234db293f1913438090d533ed47c0b9e12dc8c7627a802a44ed6 AS build
WORKDIR /build
RUN apk add --no-cache maven
COPY pom.xml .
RUN mvn dependency:go-offline -q
COPY src ./src
# Tests run in CI (mvn verify); the image build skips them.
RUN mvn package -Dmaven.test.skip=true -q

FROM eclipse-temurin:25-jre-alpine@sha256:b7528962e65d43064d8a8b67ba175367896bc948363ea2d3fcd7f10d34e1f048
WORKDIR /app
RUN adduser -S -D -H -u 10001 app
COPY --from=build --chown=app /build/target/spring-app-*.jar app.jar
USER 10001:10001
EXPOSE 8082
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=5 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8082/actuator/health"]
CMD ["java", "-jar", "app.jar"]
