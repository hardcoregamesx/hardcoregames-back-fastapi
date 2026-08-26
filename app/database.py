import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# echo estaba fijo en True: SQLAlchemy imprimia cada sentencia SQL con sus
# parametros por stdout, docker la capturaba en el json-file y cada request
# generaba entre 8 y 15 lineas de log. El 26/08/2026 eso supuso 37.714 lineas
# en 5,5 horas y fue el principal consumidor de CPU del contenedor (formateo
# de strings + escritura + encoding json por linea), con el servidor a 2 vCPU.
# Se deja detras de una variable de entorno para poder depurar sin recompilar:
#   docker compose run -e SQL_ECHO=true ...
SQL_ECHO = os.getenv("SQL_ECHO", "false").strip().lower() in ("1", "true", "yes")

engine = create_async_engine(
    DATABASE_URL,
    echo=SQL_ECHO,
    # El pool venia con los defaults (5 conexiones, 10 de overflow). Bajo el
    # pico de trafico de la madrugada eso encola requests esperando conexion.
    pool_size=10,
    max_overflow=20,
    # Recicla conexiones antes de que Postgres o el bridge de docker las corte
    # en silencio, y valida con un ping antes de entregarlas: sin esto, tras un
    # reinicio de hc-postgres el primer request de cada conexion muerta falla.
    pool_recycle=1800,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
