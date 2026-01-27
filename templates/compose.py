AGENT_POSTGRES_SNIPPET = """
  ${SERVICE_NAME}:
    container_name: ${PROJECT_NAME}-${SERVICE_NAME}
    image: postgres:17-alpine
    networks:
      - portabase
      - default
    ports:
      - "${PORT}:5432"
    volumes:
      - ${VOL_NAME}:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=${DB_NAME}
      - POSTGRES_USER=${USER}
      - POSTGRES_PASSWORD=${PASSWORD}
"""

AGENT_MARIADB_SNIPPET = """
  ${SERVICE_NAME}:
    container_name: ${PROJECT_NAME}-${SERVICE_NAME}
    image: mariadb:latest
    ports:
      - "${PORT}:3306"
    environment:
      - MYSQL_DATABASE=${DB_NAME}
      - MYSQL_USER=${USER}
      - MYSQL_PASSWORD=${PASSWORD}
      - MYSQL_RANDOM_ROOT_PASSWORD=yes
    volumes:
      - ${VOL_NAME}:/var/lib/mysql
"""

AGENT_MONGODB_AUTH_SNIPPET = """
  ${SERVICE_NAME}:
    container_name: ${PROJECT_NAME}-${SERVICE_NAME}
    image: mongo:latest
    ports:
      - "${PORT}:27017"
    environment:
      - MONGO_INITDB_ROOT_USERNAME=${USER}
      - MONGO_INITDB_ROOT_PASSWORD=${PASSWORD}
      - MONGO_INITDB_DATABASE=${DB_NAME}
    command: mongod --auth
    volumes:
      - ${VOL_NAME}:/data/db
"""

AGENT_MONGODB_SNIPPET = """
  ${SERVICE_NAME}:
    container_name: ${PROJECT_NAME}-${SERVICE_NAME}
    image: mongo:latest
    ports:
      - "${PORT}:27017"
    environment:
      - MONGO_INITDB_DATABASE=${DB_NAME}
    volumes:
      - ${VOL_NAME}:/data/db
"""



