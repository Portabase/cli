AGENT_POSTGRES_SNIPPET = """
  ${SERVICE_NAME}:
    image: postgres:17-alpine
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "${PORT}:5432"
    volumes:
      - ${VOL_NAME}:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=${DB_NAME}
      - POSTGRES_USER=${USER}
      - POSTGRES_PASSWORD=${PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${USER} -d ${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5
"""

AGENT_MARIADB_SNIPPET = """
  ${SERVICE_NAME}:
    image: mariadb:latest
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "${PORT}:3306"
    environment:
      - MYSQL_DATABASE=${DB_NAME}
      - MYSQL_USER=${USER}
      - MYSQL_PASSWORD=${PASSWORD}
      - MYSQL_RANDOM_ROOT_PASSWORD=yes
    volumes:
      - ${VOL_NAME}:/var/lib/mysql
    healthcheck:
      test: ["CMD-SHELL", "mariadb-admin ping -h localhost -u ${USER} -p${PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 5
"""

AGENT_MONGODB_AUTH_SNIPPET = """
  ${SERVICE_NAME}:
    image: mongo:latest
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "${PORT}:27017"
    environment:
      - MONGO_INITDB_ROOT_USERNAME=${USER}
      - MONGO_INITDB_ROOT_PASSWORD=${PASSWORD}
      - MONGO_INITDB_DATABASE=${DB_NAME}
    command: mongod --auth
    volumes:
      - ${VOL_NAME}:/data/db
    healthcheck:
      test: ["CMD-SHELL", "mongosh --eval 'db.runCommand({ping:1})' --quiet"]
      interval: 10s
      timeout: 5s
      retries: 5
"""

AGENT_MONGODB_SNIPPET = """
  ${SERVICE_NAME}:
    image: mongo:latest
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "${PORT}:27017"
    environment:
      - MONGO_INITDB_DATABASE=${DB_NAME}
    volumes:
      - ${VOL_NAME}:/data/db
    healthcheck:
      test: ["CMD-SHELL", "mongosh --eval 'db.runCommand({ping:1})' --quiet"]
      interval: 10s
      timeout: 5s
      retries: 5
"""

AGENT_FIREBIRD_SNIPPET = """
  ${SERVICE_NAME}:
    image: firebirdsql/firebird
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "${PORT}:3050"
    volumes:
      - ${VOL_NAME}:/var/lib/firebird/data
    environment:
      - FIREBIRD_DATABASE=${DB_NAME}
      - FIREBIRD_USER=${USER}
      - FIREBIRD_PASSWORD=${PASSWORD}
      - FIREBIRD_ROOT_PASSWORD=${ROOT_PASSWORD}
      - FIREBIRD_DATABASE_DEFAULT_CHARSET=UTF8
    healthcheck:
      test: ["CMD-SHELL", "nc -z localhost 3050"]
      interval: 10s
      timeout: 5s
      retries: 5
"""
