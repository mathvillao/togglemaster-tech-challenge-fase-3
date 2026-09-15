FROM golang:1.25-alpine3.24 AS builder

WORKDIR /app

COPY go.mod ./

COPY . .
RUN go mod tidy
RUN go build -o auth-service .

FROM alpine:3.24

WORKDIR /app

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

COPY --from=builder /app/auth-service .

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8001

CMD ["./auth-service"]