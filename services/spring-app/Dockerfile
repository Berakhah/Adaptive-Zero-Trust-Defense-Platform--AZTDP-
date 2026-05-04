FROM eclipse-temurin:25-jdk-alpine AS build
WORKDIR /build
RUN apk add --no-cache maven
COPY pom.xml .
RUN mvn dependency:go-offline -q
COPY src ./src
RUN mvn package -Dmaven.test.skip=true -q

FROM eclipse-temurin:25-jre-alpine
WORKDIR /app
COPY --from=build /build/target/spring-app-*.jar app.jar
EXPOSE 8082
CMD ["java", "-jar", "app.jar"]
