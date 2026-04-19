update:
	docker-compose --env-file .env up -d --force-recreate
clear-database:
	docker compose down influxdb
	docker volume rm fr24feed_influxdb_data
	docker compose --env-file .env up -d
