#!/bin/sh

# create a new admin user with same username and password
docker exec -it matrix_synapse register_new_matrix_user http://localhost:8008 -c /data/homeserver.yaml -u $1 -p$1 -a