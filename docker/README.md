# Setting up a matrix synapse homeserver for development

> The docker-compose file is only meant for development purposes!


## Setting synapse with docker-compose

You find more information about running synapse in a docker container here
https://github.com/matrix-org/synapse/blob/develop/docker/README.md


1. You have to create a home server configuration file

````
docker run -it --rm \
    -v $(pwd)/files:/data \
    -e SYNAPSE_SERVER_NAME=localhost \
    -e SYNAPSE_REPORT_STATS=yes \
    matrixdotorg/synapse:latest generate
````

2. Now create some folders within the docker folder

````
mkdir files
mkdir logs
mkdir files/media_store
````
and set proper access rights

2. Next you can start the complete stack

````
docker-compose up
````

> The docker compse file uses the default passwords from the generated homeserver.yaml file. Again, this is only for development!

3. Now you have to create some useres

You can use the createuser.sh script to create users

````
# this will create a admin user with username foto and password foto
# the matrix username is @foto:localhost
./createuser.sh foto
````

# Access element web

You now can access the element web client (don't forget to switch the homeserver to http://localhost:8008)

````
http://localhost:8449/#/welcome
````