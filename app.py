import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time
import sqlite3
import os
from pathlib import Path
from streamlit import errors as _st_errors

# Configuración de la página
st.set_page_config(
    page_title="Torneo de Dominó Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado para mejor diseño
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: bold;
    }
    .sub-header {
        font-size: 1.8rem;
        color: #2563EB;
        margin: 1.5rem 0rem 1rem 0rem;
        border-bottom: 2px solid #2563EB;
        padding-bottom: 0.5rem;
    }
    .card {
        background-color: #F8FAFC;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #2563EB;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 1rem 0rem;
    }
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
    }
    .success-card {
        background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
    }
    .warning-card {
        background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Archivo de base de datos SQLite
DATA_DIR = Path(__file__).parent
DB_FILE = DATA_DIR / "torneo.db"


def safe_get_secret(key, default=None):
    """Intentar leer primero desde variables de entorno, luego desde st.secrets si está disponible.
    Evita que la ausencia de un secrets.toml lance una excepción.
    """
    val = os.environ.get(key)
    if val is not None:
        return val
    try:
        # st.secrets.get puede lanzar si no hay fichero de secretos
        return st.secrets.get(key, default)
    except Exception:
        try:
            return st.secrets[key]
        except Exception:
            return default


# Nota: la contraseña está embebida directamente en el código (uso personal)
# Para ingresar al panel, usa: "admin123"


def maybe_rerun():
    """Intentar forzar una recarga segura de la app. Si `st.experimental_rerun` no existe,
    se muestra un aviso para recargar manualmente y se detiene la ejecución.
    """
    try:
        # método preferido
        return st.experimental_rerun()
    except Exception:
        # Si no está disponible, no detener la ejecución: continuar para que el panel se muestre.
        # Algunas versiones de Streamlit no exponen `experimental_rerun`; en ese caso
        # simplemente no intentamos reiniciar y dejamos que la ejecución continúe.
        return None


def get_conn():
    # Si existe DATABASE_URL en env o en secrets, conectar a Postgres
    db_url = safe_get_secret("DATABASE_URL", None)
    if db_url:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            raw_conn = psycopg2.connect(db_url, sslmode='require')

            class PGConnWrapper:
                def __init__(self, conn):
                    self._conn = conn

                def cursor(self):
                    return self._conn.cursor(cursor_factory=RealDictCursor)

                def commit(self):
                    return self._conn.commit()

                def rollback(self):
                    return self._conn.rollback()

                def close(self):
                    return self._conn.close()

            return PGConnWrapper(raw_conn)
        except Exception as e:
            # Fallback a sqlite si falla la conexión a Postgres
            st.warning(f"Fallo al conectar a Postgres, usando SQLite. Error: {e}")

    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    cur = conn.cursor()
    # Eliminar tabla config si existe (limpiar cualquier contraseña almacenada previamente)
    try:
        cur.execute("DROP TABLE IF EXISTS config")
    except Exception:
        pass
    # Tabla equipos (parejas / "cruz")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS equipos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        jugador1 TEXT NOT NULL,
        jugador2 TEXT NOT NULL,
        puntos_total INTEGER DEFAULT 0,
        partidos_jugados INTEGER DEFAULT 0,
        partidos_ganados INTEGER DEFAULT 0,
        partidos_perdidos INTEGER DEFAULT 0
    )
    """)
    # Tabla partidos
    cur.execute("""
    CREATE TABLE IF NOT EXISTS partidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ronda INTEGER,
        equipo1_id INTEGER,
        equipo2_id INTEGER,
        puntos_e1 INTEGER,
        puntos_e2 INTEGER,
        rounds_json TEXT,
        ganador_id INTEGER,
        match_pts_e1 INTEGER DEFAULT 0,
        match_pts_e2 INTEGER DEFAULT 0,
        fecha TEXT,
        FOREIGN KEY(equipo1_id) REFERENCES equipos(id),
        FOREIGN KEY(equipo2_id) REFERENCES equipos(id),
        FOREIGN KEY(ganador_id) REFERENCES equipos(id)
    )
    """)
    # Asegurar columnas legacy/alter
    try:
        cur.execute("ALTER TABLE partidos ADD COLUMN match_pts_e1 INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE partidos ADD COLUMN match_pts_e2 INTEGER DEFAULT 0")
    except Exception:
        pass
    # no se guardan configuraciones en tabla para uso personal
    conn.commit()
    conn.close()


# No se usa almacenamiento de contraseña; uso contraseña fija en código para uso personal


def load_data():
    """Carga jugadores y partidos desde la base de datos."""
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    equipos = []
    partidos = []
    try:
        cur.execute("SELECT id, nombre, jugador1, jugador2, puntos_total, partidos_jugados, partidos_ganados, partidos_perdidos FROM equipos")
        equipos = [dict(row) for row in cur.fetchall()]
        cur.execute("""
        SELECT p.id, p.ronda, e1.nombre AS equipo1, e2.nombre AS equipo2,
               p.puntos_e1 AS puntos_j1, p.puntos_e2 AS puntos_j2,
               p.rounds_json AS rounds_json, p.match_pts_e1 AS match_pts_e1, p.match_pts_e2 AS match_pts_e2,
               COALESCE(e3.nombre, 'Empate') AS ganador, p.fecha
        FROM partidos p
        LEFT JOIN equipos e1 ON p.equipo1_id = e1.id
        LEFT JOIN equipos e2 ON p.equipo2_id = e2.id
        LEFT JOIN equipos e3 ON p.ganador_id = e3.id
        ORDER BY p.id ASC
        """)
        partidos = [dict(row) for row in cur.fetchall()]
    except Exception as e:
        st.warning(f"No se pudieron cargar los datos desde la base: {e}")
    finally:
        conn.close()
    return equipos, partidos


def add_team_db(nombre, jugador1, jugador2):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO equipos (nombre, jugador1, jugador2, puntos_total, partidos_jugados, partidos_ganados, partidos_perdidos) VALUES (?,?,?,?,0,0,0)",
            (nombre, jugador1, jugador2, 0)
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError:
        new_id = None
    finally:
        conn.close()
    return new_id


def add_partido_db(ronda, equipo1_name, equipo2_name, rounds_list, fecha):
    """Guarda un partido compuesto por varias rondas.
    `rounds_list` es una lista de dicts: [{'puntos_e1': int, 'puntos_e2': int}, ...]
    """
    import json as _json
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Obtener ids de equipos
        cur.execute("SELECT id FROM equipos WHERE nombre = ?", (equipo1_name,))
        r1 = cur.fetchone()
        cur.execute("SELECT id FROM equipos WHERE nombre = ?", (equipo2_name,))
        r2 = cur.fetchone()
        if not r1 or not r2:
            st.warning("Uno de los equipos no existe en la base de datos")
            return None
        equipo1_id = r1['id']
        equipo2_id = r2['id']

        # Calcular totales y sets ganados
        total_e1 = 0
        total_e2 = 0
        sets_e1 = 0
        sets_e2 = 0
        rounds_serializable = []
        for rd in rounds_list:
            pe1 = int(rd.get('puntos_e1', 0))
            pe2 = int(rd.get('puntos_e2', 0))
            total_e1 += pe1
            total_e2 += pe2
            # determinar ganador de la ronda: ahora se considera ganada solo si es exactamente 100
            if pe1 == 100 or pe2 == 100:
                if pe1 == 100 and pe2 != 100:
                    sets_e1 += 1
                    winner = equipo1_id
                elif pe2 == 100 and pe1 != 100:
                    sets_e2 += 1
                    winner = equipo2_id
                else:
                    # ambos 100 -> empate de ronda
                    winner = None
            else:
                # si ninguno llegó a 100, decidir por quien tiene más puntos
                if pe1 > pe2:
                    sets_e1 += 1
                    winner = equipo1_id
                elif pe2 > pe1:
                    sets_e2 += 1
                    winner = equipo2_id
                else:
                    winner = None
            rounds_serializable.append({'puntos_e1': pe1, 'puntos_e2': pe2, 'winner_id': winner})

        # Determinar ganador del partido (mejor de 3 -> primero a 2 sets)
        if sets_e1 >= 2:
            ganador_id = equipo1_id
        elif sets_e2 >= 2:
            ganador_id = equipo2_id
        else:
            ganador_id = None

        rounds_json = _json.dumps(rounds_serializable, ensure_ascii=False)

        # Evitar que se juegue dos veces el mismo enfrentamiento (independientemente del orden)
        cur.execute("SELECT id FROM partidos WHERE (equipo1_id = ? AND equipo2_id = ?) OR (equipo1_id = ? AND equipo2_id = ?)", (equipo1_id, equipo2_id, equipo2_id, equipo1_id))
        existing = cur.fetchone()
        if existing:
            st.warning("❌ Ya existe un partido entre estos equipos. No se permiten duplicados.")
            return None

        # Determinar puntos de liga por partido: ganador 3, empate 1 cada uno, perdedor 0
        if ganador_id == equipo1_id:
            match_pts_e1 = 3
            match_pts_e2 = 0
        elif ganador_id == equipo2_id:
            match_pts_e1 = 0
            match_pts_e2 = 3
        else:
            match_pts_e1 = 1
            match_pts_e2 = 1

        cur.execute(
            "INSERT INTO partidos (ronda, equipo1_id, equipo2_id, puntos_e1, puntos_e2, rounds_json, ganador_id, match_pts_e1, match_pts_e2, fecha) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ronda, equipo1_id, equipo2_id, total_e1, total_e2, rounds_json, ganador_id, match_pts_e1, match_pts_e2, fecha)
        )

        # Actualizar estadísticas de equipos (puntos de liga)
        cur.execute("UPDATE equipos SET partidos_jugados = partidos_jugados + 1, puntos_total = puntos_total + ? WHERE id = ?", (match_pts_e1, equipo1_id))
        cur.execute("UPDATE equipos SET partidos_jugados = partidos_jugados + 1, puntos_total = puntos_total + ? WHERE id = ?", (match_pts_e2, equipo2_id))
        if ganador_id is not None:
            cur.execute("UPDATE equipos SET partidos_ganados = partidos_ganados + 1 WHERE id = ?", (ganador_id,))
            loser_id = equipo2_id if ganador_id == equipo1_id else equipo1_id
            cur.execute("UPDATE equipos SET partidos_perdidos = partidos_perdidos + 1 WHERE id = ?", (loser_id,))

        conn.commit()
        new_id = cur.lastrowid
    except Exception as e:
        conn.rollback()
        st.warning(f"Error guardando partido en DB: {e}")
        new_id = None
    finally:
        conn.close()
    return new_id


# Inicializar session state (cargar persistencia si existe)
if 'partidos' not in st.session_state or 'equipos' not in st.session_state:
    equipos, partidos = load_data()
    st.session_state.partidos = partidos or []
    st.session_state.equipos = equipos or []
if 'ronda_actual' not in st.session_state:
    st.session_state.ronda_actual = 1
# Estado de sesión para autenticación de organizador
if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False

# Función para calcular estadísticas
def calcular_estadisticas():
    for equipo in st.session_state.equipos:
        nombre = equipo.get('nombre')
        equipo['partidos_jugados'] = len([p for p in st.session_state.partidos 
                                         if nombre in [p.get('equipo1'), p.get('equipo2')]])
        equipo['partidos_ganados'] = len([p for p in st.session_state.partidos 
                                         if p.get('ganador') == nombre])
        equipo['partidos_perdidos'] = len([p for p in st.session_state.partidos 
                                         if (p.get('equipo1') == nombre or p.get('equipo2') == nombre) and p.get('ganador') not in (None, 'Empate', nombre)])

# Función para agregar partido
def agregar_partido(equipo1_name, equipo2_name, rounds_list):
    """Recibe nombres de equipos y una lista de rondas [{'puntos_e1':int,'puntos_e2':int}, ...]"""
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_id = add_partido_db(st.session_state.ronda_actual, equipo1_name, equipo2_name, rounds_list, fecha)
    if new_id:
        equipos, partidos = load_data()
        st.session_state.equipos = equipos or []
        st.session_state.partidos = partidos or []
        calcular_estadisticas()
    else:
        st.warning("No se pudo guardar el partido en la base de datos")


def update_partido_db(partido_id, rounds_list):
    """Actualiza un partido existente (recalcula sets, puntos y actualiza estadísticas de equipos)."""
    import json as _json
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,))
        row = cur.fetchone()
        if not row:
            st.error("Partido no encontrado")
            return False

        equipo1_id = row['equipo1_id']
        equipo2_id = row['equipo2_id']
        old_match_pts_e1 = row['match_pts_e1'] or 0
        old_match_pts_e2 = row['match_pts_e2'] or 0
        old_ganador = row['ganador_id']

        # Calcular nuevos valores
        total_e1 = 0
        total_e2 = 0
        sets_e1 = 0
        sets_e2 = 0
        rounds_serializable = []
        for rd in rounds_list:
            pe1 = int(rd.get('puntos_e1', 0))
            pe2 = int(rd.get('puntos_e2', 0))
            total_e1 += pe1
            total_e2 += pe2
            # Validación: ronda ganada solo si es exactamente 100
            if pe1 == 100 or pe2 == 100:
                if pe1 == 100 and pe2 != 100:
                    sets_e1 += 1
                    winner = equipo1_id
                elif pe2 == 100 and pe1 != 100:
                    sets_e2 += 1
                    winner = equipo2_id
                else:
                    winner = None
            else:
                if pe1 > pe2:
                    sets_e1 += 1
                    winner = equipo1_id
                elif pe2 > pe1:
                    sets_e2 += 1
                    winner = equipo2_id
                else:
                    winner = None
            rounds_serializable.append({'puntos_e1': pe1, 'puntos_e2': pe2, 'winner_id': winner})

        if sets_e1 >= 2:
            new_ganador = equipo1_id
        elif sets_e2 >= 2:
            new_ganador = equipo2_id
        else:
            new_ganador = None

        if new_ganador == equipo1_id:
            new_match_pts_e1, new_match_pts_e2 = 3, 0
        elif new_ganador == equipo2_id:
            new_match_pts_e1, new_match_pts_e2 = 0, 3
        else:
            new_match_pts_e1, new_match_pts_e2 = 1, 1

        rounds_json = _json.dumps(rounds_serializable, ensure_ascii=False)

        # Ajustar estadísticas de equipos: sustituir puntos de liga antiguos por nuevos
        # Restar antiguos match pts
        cur.execute("UPDATE equipos SET puntos_total = puntos_total - ? WHERE id = ?", (old_match_pts_e1, equipo1_id))
        cur.execute("UPDATE equipos SET puntos_total = puntos_total - ? WHERE id = ?", (old_match_pts_e2, equipo2_id))
        # Aplicar nuevos match pts
        cur.execute("UPDATE equipos SET puntos_total = puntos_total + ? WHERE id = ?", (new_match_pts_e1, equipo1_id))
        cur.execute("UPDATE equipos SET puntos_total = puntos_total + ? WHERE id = ?", (new_match_pts_e2, equipo2_id))

        # Ajustar ganados/perdidos si cambió el ganador
        if old_ganador != new_ganador:
            # Decrementar conteos del ganador antiguo
            if old_ganador is not None:
                cur.execute("UPDATE equipos SET partidos_ganados = partidos_ganados - 1 WHERE id = ?", (old_ganador,))
                loser_old = equipo2_id if old_ganador == equipo1_id else equipo1_id
                cur.execute("UPDATE equipos SET partidos_perdidos = partidos_perdidos - 1 WHERE id = ?", (loser_old,))
            # Incrementar conteos del nuevo ganador
            if new_ganador is not None:
                cur.execute("UPDATE equipos SET partidos_ganados = partidos_ganados + 1 WHERE id = ?", (new_ganador,))
                loser_new = equipo2_id if new_ganador == equipo1_id else equipo1_id
                cur.execute("UPDATE equipos SET partidos_perdidos = partidos_perdidos + 1 WHERE id = ?", (loser_new,))

        # Actualizar la fila de partido
        cur.execute(
            "UPDATE partidos SET puntos_e1 = ?, puntos_e2 = ?, rounds_json = ?, ganador_id = ?, match_pts_e1 = ?, match_pts_e2 = ?, fecha = ? WHERE id = ?",
            (total_e1, total_e2, rounds_json, new_ganador, new_match_pts_e1, new_match_pts_e2, datetime.now().strftime("%Y-%m-%d %H:%M"), partido_id)
        )

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.warning(f"Error actualizando partido: {e}")
        return False
    finally:
        conn.close()


def delete_partido_db(partido_id):
    """Elimina un partido y ajusta las estadísticas de los equipos afectados."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,))
        row = cur.fetchone()
        if not row:
            st.error("Partido no encontrado")
            return False
        equipo1_id = row['equipo1_id']
        equipo2_id = row['equipo2_id']
        match_pts_e1 = row['match_pts_e1'] or 0
        match_pts_e2 = row['match_pts_e2'] or 0
        ganador = row['ganador_id']

        # Restar puntos de liga y partidos jugados
        cur.execute("UPDATE equipos SET puntos_total = puntos_total - ?, partidos_jugados = partidos_jugados - 1 WHERE id = ?", (match_pts_e1, equipo1_id))
        cur.execute("UPDATE equipos SET puntos_total = puntos_total - ?, partidos_jugados = partidos_jugados - 1 WHERE id = ?", (match_pts_e2, equipo2_id))

        # Ajustar ganados/perdidos si corresponde
        if ganador is not None:
            cur.execute("UPDATE equipos SET partidos_ganados = partidos_ganados - 1 WHERE id = ?", (ganador,))
            loser = equipo2_id if ganador == equipo1_id else equipo1_id
            cur.execute("UPDATE equipos SET partidos_perdidos = partidos_perdidos - 1 WHERE id = ?", (loser,))

        # Finalmente borrar el partido
        cur.execute("DELETE FROM partidos WHERE id = ?", (partido_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.warning(f"Error eliminando partido: {e}")
        return False
    finally:
        conn.close()


def clear_database():
    """Elimina todos los partidos y equipos (limpieza total)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM partidos")
        cur.execute("DELETE FROM equipos")
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.warning(f"Error limpiando la base de datos: {e}")
        return False
    finally:
        conn.close()

# Header principal
st.markdown('<div class="main-header">🏆 TORNEO DE DOMINÓ PRO</div>', unsafe_allow_html=True)


def centered_heading(text, level=3):
    """Muestra un encabezado centrado en la página."""
    tag = f"h{level}"
    st.markdown(f"<{tag} style=\"text-align:center\">{text}</{tag}>", unsafe_allow_html=True)


def centered_subheader(text):
    """Muestra un sub-encabezado (clase sub-header) centrado."""
    st.markdown(f'<div class="sub-header" style="text-align:center">{text}</div>', unsafe_allow_html=True)

# Sidebar para modo de vista
st.sidebar.markdown("## 🎮 Configuración del Torneo")
modo = st.sidebar.radio("Selecciona el modo:", ["👀 Vista Espectador", "⚙️ Panel Organizador"])

if modo == "⚙️ Panel Organizador":
    # Login simple usando la contraseña fija en código (uso personal)
    # Handler que se dispara cuando el usuario presiona Enter en el text_input
    def attempt_login_from_sidebar():
        pwd = st.session_state.get('side_login', '')
        if (pwd or '').strip() == "admin123":
            st.session_state.is_admin = True
            st.sidebar.success('✅ Acceso concedido como Organizador')
            maybe_rerun()
        else:
            if pwd != "":
                # Mostrar error solo si hubo entrada (evita mostrar al cargar la página)
                st.sidebar.error('❌ Contraseña incorrecta')

    contraseña = st.sidebar.text_input("🔑 Contraseña de Organizador", type="password", key='side_login', on_change=attempt_login_from_sidebar)

    # Mantener botón como alternativa por si el on_change no se dispara en alguna versión
    if st.sidebar.button('Iniciar sesión'):
        pwd = st.session_state.get('side_login', '')
        if (pwd or '').strip() == "admin123":
            st.session_state.is_admin = True
            st.sidebar.success('✅ Acceso concedido como Organizador')
            maybe_rerun()
        else:
            st.sidebar.error('❌ Contraseña incorrecta')

    if st.session_state.is_admin:
        if st.sidebar.button('Cerrar sesión'):
            st.session_state.is_admin = False
            maybe_rerun()

    # Botón de depuración: forzar login local (útil si hay problemas con el input)
    # (Botón de depuración eliminado)

    # Mostrar panel si está autenticado
    if st.session_state.is_admin:
        centered_subheader('⚙️ Panel de Control del Organizador')
        
        # Estadísticas rápidas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f'<div class="stat-card"><h3>👥 Equipos</h3><h2>{len(st.session_state.equipos)}</h2></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="stat-card"><h3>🎯 Partidos</h3><h2>{len(st.session_state.partidos)}</h2></div>', unsafe_allow_html=True)
        with col3:
            total_puntos = sum(equipo.get('puntos_total', 0) for equipo in st.session_state.equipos)
            st.markdown(f'<div class="stat-card"><h3>⭐ Puntos Totales</h3><h2>{total_puntos}</h2></div>', unsafe_allow_html=True)
        
        # Sección para ingresar resultados
        centered_subheader('📝 Ingresar Resultados')

        # Nota: la contraseña del organizador está embebida en el código (por uso personal)
        centered_subheader('🔐 Configuración de Contraseña')
        st.info('La contraseña de organizador es fija para uso local. Cambia `ADMIN_PASS` en el código si lo deseas.')

        if len(st.session_state.equipos) >= 2:
            # evitar seleccionar rivales ya jugados
            equipo1 = st.selectbox("Equipo 1", [j['nombre'] for j in st.session_state.equipos], key="ing_e1")
            # construir lista de rivales no jugados
            jugados_por_e1 = set()
            for p in st.session_state.partidos:
                if p.get('equipo1') == equipo1:
                    jugados_por_e1.add(p.get('equipo2'))
                elif p.get('equipo2') == equipo1:
                    jugados_por_e1.add(p.get('equipo1'))
            otros_equipos = [j['nombre'] for j in st.session_state.equipos if j['nombre'] != equipo1 and j['nombre'] not in jugados_por_e1]
            if not otros_equipos:
                st.info("No hay oponentes disponibles que no hayan jugado ya contra este equipo.")
            else:
                with st.form("form_resultado", clear_on_submit=True):
                    equipo2 = st.selectbox("Equipo 2", otros_equipos, key="ing_e2")
                    st.markdown("**Ingresa los puntos por ronda (una ronda finaliza cuando un equipo tiene exactamente 100 pts).**")

                    # Rondas 1 y 2 siempre visibles
                    c1, c2 = st.columns(2)
                    with c1:
                        r1_p1 = st.number_input(f"Ronda 1 - Puntos {equipo1}", min_value=0, max_value=500, value=0, key=f"ing_r1_e1_{equipo1}_{equipo2}")
                    with c2:
                        r1_p2 = st.number_input(f"Ronda 1 - Puntos {equipo2}", min_value=0, max_value=500, value=0, key=f"ing_r1_e2_{equipo1}_{equipo2}")

                    c3, c4 = st.columns(2)
                    with c3:
                        r2_p1 = st.number_input(f"Ronda 2 - Puntos {equipo1}", min_value=0, max_value=500, value=0, key=f"ing_r2_e1_{equipo1}_{equipo2}")
                    with c4:
                        r2_p2 = st.number_input(f"Ronda 2 - Puntos {equipo2}", min_value=0, max_value=500, value=0, key=f"ing_r2_e2_{equipo1}_{equipo2}")

                    # calcular sets ganados tras 2 rondas con la regla ==100
                    sets_e1 = 0
                    sets_e2 = 0
                    # Ronda 1
                    if r1_p1 == 100 and r1_p2 != 100:
                        sets_e1 += 1
                    elif r1_p2 == 100 and r1_p1 != 100:
                        sets_e2 += 1
                    else:
                        if r1_p1 > r1_p2:
                            sets_e1 += 1
                        elif r1_p2 > r1_p1:
                            sets_e2 += 1
                    # Ronda 2
                    if r2_p1 == 100 and r2_p2 != 100:
                        sets_e1 += 1
                    elif r2_p2 == 100 and r2_p1 != 100:
                        sets_e2 += 1
                    else:
                        if r2_p1 > r2_p2:
                            sets_e1 += 1
                        elif r2_p2 > r2_p1:
                            sets_e2 += 1

                    rounds_list = [{'puntos_e1': int(r1_p1), 'puntos_e2': int(r1_p2)}, {'puntos_e1': int(r2_p1), 'puntos_e2': int(r2_p2)}]

                    # Mostrar/ocultar Ronda 3: si alguno ya tiene 2 sets, no mostrar
                    show_r3 = not (sets_e1 >= 2 or sets_e2 >= 2)
                    if show_r3:
                        c5, c6 = st.columns(2)
                        with c5:
                            r3_p1 = st.number_input(f"Ronda 3 - Puntos {equipo1}", min_value=0, max_value=500, value=0, key=f"ing_r3_e1_{equipo1}_{equipo2}")
                        with c6:
                            r3_p2 = st.number_input(f"Ronda 3 - Puntos {equipo2}", min_value=0, max_value=500, value=0, key=f"ing_r3_e2_{equipo1}_{equipo2}")
                        rounds_list.append({'puntos_e1': int(r3_p1), 'puntos_e2': int(r3_p2)})

                    submitted = st.form_submit_button("🎯 Guardar Resultado del Partido", use_container_width=True)
                    if submitted:
                        if not equipo1 or not equipo2 or equipo1 == equipo2:
                            st.error("❌ Selecciona equipos diferentes")
                        else:
                            new_id = add_partido_db(st.session_state.ronda_actual, equipo1, equipo2, rounds_list, datetime.now().strftime("%Y-%m-%d %H:%M"))
                            if new_id:
                                equipos, partidos = load_data()
                                st.session_state.equipos = equipos or []
                                st.session_state.partidos = partidos or []
                                calcular_estadisticas()
                                st.success(f"✅ Partido registrado: {equipo1} vs {equipo2}")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ No se pudo guardar el partido (posible duplicado o error)")
        else:
            st.info("➕ Agrega al menos 2 equipos para poder ingresar resultados")
        
        # Gestión de equipos
        centered_subheader('👥 Gestión de Equipos')
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Mostrar equipos con sus columnas relevantes
            df = pd.DataFrame(st.session_state.equipos)
            if not df.empty:
                df = df[['id', 'nombre', 'jugador1', 'jugador2', 'puntos_total', 'partidos_ganados', 'partidos_perdidos', 'partidos_jugados']]
            st.dataframe(df, use_container_width=True)
        
        with col2:
            with st.form("nuevo_equipo"):
                nombre_equipo = st.text_input("Nombre del equipo (opcional)")
                jugador_a = st.text_input("Jugador A (nombre)")
                jugador_b = st.text_input("Jugador B (nombre)")
                if st.form_submit_button("➕ Agregar Equipo"):
                    if not jugador_a or not jugador_b:
                        st.error("❌ Ingresa los nombres de ambos jugadores")
                    else:
                        if not nombre_equipo:
                            nombre_equipo = f"{jugador_a} & {jugador_b}"
                        new_id = add_team_db(nombre_equipo, jugador_a, jugador_b)
                        if new_id:
                            equipos, partidos = load_data()
                            st.session_state.equipos = equipos or []
                            st.session_state.partidos = partidos or []
                            st.success(f"✅ Equipo '{nombre_equipo}' agregado")
                            st.rerun()
                        else:
                            st.error(f"❌ No se pudo agregar. El nombre de equipo '{nombre_equipo}' ya existe o hubo un error.")
            
            # (Control de Ronda eliminado por solicitud)
        # Editor de partidos (corrección)
        centered_subheader('✏️ Editor de Partidos')
        partidos_list = st.session_state.partidos
        if partidos_list:
            opciones = [f"{p['id']}: {p.get('equipo1')} vs {p.get('equipo2')}" for p in partidos_list]
            sel = st.selectbox("Selecciona partido a editar", opciones)
            if sel:
                partido_id = int(sel.split(":")[0])
                partido_row = next((p for p in partidos_list if p['id'] == partido_id), None)
                if partido_row:
                    import json as _json
                    rounds_existing = []
                    try:
                        rounds_existing = _json.loads(partido_row.get('rounds_json') or '[]')
                    except Exception:
                        rounds_existing = []

                    default_index = max(0, min(len(rounds_existing)-1, 2)) if rounds_existing else 0
                    current_rondas = st.selectbox("Rondas", [1,2,3], index=default_index, key=f"edit_rondas_{partido_id}")
                    with st.form(f"edit_partido_{partido_id}"):
                        edit_rounds = []
                        for i in range(1, current_rondas+1):
                            existing = rounds_existing[i-1] if i-1 < len(rounds_existing) else {}
                            c1, c2 = st.columns(2)
                            with c1:
                                default_v1 = int(existing.get('puntos_e1', 0))
                                v1 = st.number_input(f"Ronda {i} - Puntos {partido_row.get('equipo1')}", min_value=0, max_value=500, value=default_v1, key=f"edit_{partido_id}_r{i}_e1_{current_rondas}")
                            with c2:
                                default_v2 = int(existing.get('puntos_e2', 0))
                                v2 = st.number_input(f"Ronda {i} - Puntos {partido_row.get('equipo2')}", min_value=0, max_value=500, value=default_v2, key=f"edit_{partido_id}_r{i}_e2_{current_rondas}")
                            edit_rounds.append({'puntos_e1': int(v1), 'puntos_e2': int(v2)})
                        if st.form_submit_button("💾 Guardar cambios"):
                            ok = update_partido_db(partido_id, edit_rounds)
                            if ok:
                                equipos, partidos = load_data()
                                st.session_state.equipos = equipos or []
                                st.session_state.partidos = partidos or []
                                st.success("✅ Partido actualizado")
                                st.rerun()
                            else:
                                st.error("❌ No se pudo actualizar el partido")
                    # Opción para eliminar el partido
                    st.markdown("---")
                    confirmar = st.checkbox("Confirmar eliminación de este partido", key=f"confirm_del_{partido_id}")
                    if confirmar:
                        if st.button("🗑️ Eliminar partido", key=f"del_btn_{partido_id}"):
                            ok = delete_partido_db(partido_id)
                            if ok:
                                equipos, partidos = load_data()
                                st.session_state.equipos = equipos or []
                                st.session_state.partidos = partidos or []
                                st.success("✅ Partido eliminado")
                                st.rerun()
                            else:
                                st.error("❌ No se pudo eliminar el partido")
        else:
            st.info("No hay partidos para editar aún")
    
    else:
        if contraseña:
            st.sidebar.error("❌ Contraseña incorrecta")
        st.warning("🔒 Ingresa la contraseña para acceder al panel de organizador")

else:
    # VISTA DE ESPECTADORES
    centered_subheader('👀 Vista de Espectadores')

    # Selector de vista (por defecto: tabla de partidos)
    spec_view = st.radio("Ver:", ["Tabla de partidos", "Resultados completos"], index=0, key="spec_view")

    if spec_view == "Tabla de partidos":
        # Mostrar tabla de posiciones para espectadores (solicitado)
        centered_heading("🏅 Tabla de Posiciones", level=3)
        df_equipos = pd.DataFrame(st.session_state.equipos)
        if not df_equipos.empty:
            # Asegurar columnas necesarias
            for col in ['partidos_jugados','partidos_ganados','partidos_perdidos','puntos_total']:
                if col not in df_equipos.columns:
                    df_equipos[col] = 0
            df_equipos = df_equipos.sort_values(['puntos_total','partidos_ganados'], ascending=[False, False])
            df_equipos['posicion'] = range(1, len(df_equipos) + 1)
            # Añadir columna con los nombres de los jugadores del equipo
            df_equipos['jugadores'] = df_equipos.apply(lambda r: f"{r.get('jugador1','')} & {r.get('jugador2','')}", axis=1)
            df_show = df_equipos[['posicion','nombre','jugadores','partidos_jugados','partidos_ganados','partidos_perdidos','puntos_total']]
            st.dataframe(df_show.reset_index(drop=True), use_container_width=True, hide_index=True)
        else:
            st.info("📊 No hay equipos todavía")

    else:
        # Resultados completos: lista de partidos con desglose de rondas y detalles
        centered_heading("📋 Resultados Completos de Partidos", level=3)
        if st.session_state.partidos:
            import json as _json
            # selector para filtrar por equipo o ver todos
            equipos_nombres = [e['nombre'] for e in st.session_state.equipos]
            filtro = st.selectbox("Filtrar por equipo:", ["Todos"] + equipos_nombres, index=0, key="filter_resultados")
            partidos_filtrados = sorted(st.session_state.partidos, key=lambda x: x['id'], reverse=True)
            if filtro != "Todos":
                partidos_filtrados = [p for p in partidos_filtrados if filtro in (p.get('equipo1'), p.get('equipo2'))]

            if not partidos_filtrados:
                st.info("No hay partidos para mostrar con ese filtro")
            else:
                for partido in partidos_filtrados:
                    header = f"**{partido.get('equipo1')}** vs **{partido.get('equipo2')}** — Ronda {partido.get('ronda')} — Ganador: {partido.get('ganador')}"
                    if filtro != "Todos":
                        centered_heading(f"Resultados de {filtro}", level=3)
                        st.markdown(header)
                    else:
                        st.markdown(header)
                    try:
                        rounds = _json.loads(partido.get('rounds_json') or '[]')
                    except Exception:
                        rounds = []
                    if rounds:
                        rows = []
                        for idx, r in enumerate(rounds, start=1):
                            winner_tag = ''
                            if r.get('winner_id'):
                                wid = r.get('winner_id')
                                wname = next((e['nombre'] for e in st.session_state.equipos if e['id'] == wid), None)
                                winner_tag = f" — Ganador ronda: {wname}" if wname else ''
                            rows.append({'Ronda': idx, f"{partido.get('equipo1')}": r.get('puntos_e1'), f"{partido.get('equipo2')}": r.get('puntos_e2'), 'info': winner_tag})
                        st.table(pd.DataFrame(rows))
                    else:
                        st.info("No hay detalle de rondas para este partido")
                    st.markdown("---")
        else:
            st.info("Aún no hay partidos registrados")

# Footer
st.markdown("---")
st.markdown("*Sistema de Torneo de Dominó Pro • Desarrollado con Streamlit*")