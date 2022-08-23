docker build -t w2vy/p1test --platform=linux/amd64 .
docker rm flux_p1test
echo docker run --name flux_p1test --memory="1g" --cpus="1.0" -p 39289:39289 -e FLUX_PORT=39289 -e VAULT_DNS='192.168.8.13' w2vy/p1test
echo docker exec -it flux_p1test ash
echo docker stop flux_p1test

