# matrix-photos

[![Latest PyPI version](https://img.shields.io/pypi/v/matrix-photos)](https://pypi.org/project/matrix-photos/)
[![Development](https://github.com/universalappfactory/matrix-photos/actions/workflows/run-checks.yml/badge.svg)](https://github.com/universalappfactory/matrix-photos/actions/workflows/run-checks.yml)

This aims to be a simple [matrix](https://matrix.org/) client for the photOS DIY photoframe.

Matrix is an open standard for secure, decentralised, real-time communication.

For photOS please checkout https://github.com/avanc/photOS for more information.

This client can be used to transfer files (pictures/photos) to the photoframe with end to end encryption support.
The idea is, that trusted users just can create a matrix room and invite the photoframe matrix user.
The photoframe user will automatically join this room and download all media sent to this room (You can specify which mimetypes are allowed).

## Configuration

There is a config-example.yml in this project which should be mostly self-explaining.

It is possible to add textmessages to the images. This is done with the tool 'convert'.
The client automatically adds the first message after you post media content to the latest image when write_text_messages is set to true.

You can also optionally define an admin_user which can run some administration commands on the photoframe.
If you define an admin user then just send !help from the specified user to the chatroom and the client sends you a list of available commands.

## Running

Just create a virtual environement install the requirements and you can run the client.

```
    python -m matrix_photos -c /path/to/config.yml
```

## Development

If you want to develop or test the client, there is a docker-compose file in the docker directory which starts a matrix synapse homeserver,
a postgres database, an element matrix client and pgadmin if you want to check the database.
