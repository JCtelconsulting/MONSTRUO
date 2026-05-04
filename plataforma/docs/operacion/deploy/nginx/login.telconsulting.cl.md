server {
  listen 80;
  server_name login.telconsulting.cl;

  # Cuando tengas TLS, cambia a listen 443 ssl; y agrega certificados.

  location / {
    proxy_pass http://192.168.60.5:9000;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_read_timeout 120s;
    proxy_connect_timeout 30s;
  }
}

