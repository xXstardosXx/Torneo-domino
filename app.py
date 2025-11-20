import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time
import json as _json
import os
from pathlib import Path
from streamlit import errors as _st_errors

# Configuración de la página
st.set_page_config(
    page_title="Torneo de Dominó",
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
    # Esta aplicación ahora puede usar un almacenamiento JSON local (`data.json`)
    # Si hay una variable `DATABASE_URL` se podría usar Postgres, pero en esta
    # versión preferimos JSON en disco para sincronizar vía GitHub (actualizaciones
    # por push). Conservamos la función por compatibilidad, pero no abrimos
    # conexiones DB.
    return None


def init_db():
    # Inicializar archivo JSON de datos si no existe
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_file = DATA_DIR / "data.json"
    if not data_file.exists():
        base = {"equipos": [], "partidos": []}
        try:
            with open(data_file, "w", encoding="utf-8") as f:
                _json.dump(base, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.warning(f"No se pudo crear data.json: {e}")


# No se usa almacenamiento de contraseña; uso contraseña fija en código para uso personal


def load_data():
    """Carga `equipos` y `partidos` desde `data.json` y devuelve listas en el mismo
    formato que antes para minimizar cambios en la UI.

    Aplicamos una recalculación segura de estadísticas en los datos en disco
    para que los cambios de reglas (puntos solo al ganador por rondas)
    se apliquen también a partidos ya existentes.
    """
    init_db()
    data_file = DATA_DIR / "data.json"
    equipos = []
    partidos_out = []
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            store = _json.load(f)
    except Exception as e:
        st.warning(f"No se pudo leer data.json: {e}")
        store = {"equipos": [], "partidos": []}

    # Recalcular y corregir estadísticas en el store para aplicar la nueva regla
    try:
        # inicializar
        for e in store.get('equipos', []):
            e['puntos_total'] = 0
            e['partidos_jugados'] = 0
            e['partidos_ganados'] = 0
            e['partidos_perdidos'] = 0

        equipos_map = {e['id']: e for e in store.get('equipos', [])}
        for p in store.get('partidos', []):
            e1 = equipos_map.get(p.get('equipo1_id'))
            e2 = equipos_map.get(p.get('equipo2_id'))
            if not e1 or not e2:
                continue
            # contabilizar jugados
            e1['partidos_jugados'] = e1.get('partidos_jugados', 0) + 1
            e2['partidos_jugados'] = e2.get('partidos_jugados', 0) + 1
            # puntos: SOLO los bonos por rondas al ganador del partido
            if p.get('ganador_id') == e1.get('id'):
                e1['puntos_total'] = e1.get('puntos_total', 0) + (p.get('round_bonus_e1') or 0)
                equipos_map[p.get('ganador_id')]['partidos_ganados'] = equipos_map[p.get('ganador_id')].get('partidos_ganados', 0) + 1
                loser = p.get('equipo2_id') if p.get('ganador_id') == p.get('equipo1_id') else p.get('equipo1_id')
                equipos_map[loser]['partidos_perdidos'] = equipos_map[loser].get('partidos_perdidos', 0) + 1
            elif p.get('ganador_id') == e2.get('id'):
                e2['puntos_total'] = e2.get('puntos_total', 0) + (p.get('round_bonus_e2') or 0)
                equipos_map[p.get('ganador_id')]['partidos_ganados'] = equipos_map[p.get('ganador_id')].get('partidos_ganados', 0) + 1
                loser = p.get('equipo2_id') if p.get('ganador_id') == p.get('equipo1_id') else p.get('equipo1_id')
                equipos_map[loser]['partidos_perdidos'] = equipos_map[loser].get('partidos_perdidos', 0) + 1

        # persistir correcciones
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception:
        # si algo falla, no rompemos la carga; devolvemos lo que tengamos
        pass

    # Equipos: ya contienen los campos necesarios
    equipos = store.get("equipos", [])

    # Partidos: convertir ids a nombres en la estructura esperada por la UI
    equipos_by_id = {e['id']: e['nombre'] for e in equipos}
    for p in store.get("partidos", []):
        partido = {
            'id': p.get('id'),
            'ronda': p.get('ronda'),
            'equipo1': equipos_by_id.get(p.get('equipo1_id')),
            'equipo2': equipos_by_id.get(p.get('equipo2_id')),
            'puntos_j1': p.get('puntos_e1'),
            'puntos_j2': p.get('puntos_e2'),
            'rounds_json': p.get('rounds_json'),
            'match_pts_e1': p.get('match_pts_e1'),
            'match_pts_e2': p.get('match_pts_e2'),
            'ganador': equipos_by_id.get(p.get('ganador_id')) if p.get('ganador_id') is not None else 'Empate',
            'fecha': p.get('fecha')
        }
        partidos_out.append(partido)

    return equipos, partidos_out


def add_team_db(nombre, jugador1, jugador2):
    # Persistencia basada en JSON: añadir equipo a data.json
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_file = DATA_DIR / "data.json"
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            store = _json.load(f)
    except Exception:
        store = {"equipos": [], "partidos": []}

    # comprobar duplicado por nombre
    if any(e.get('nombre') == nombre for e in store.get('equipos', [])):
        return None

    next_id = 1
    ids = [e.get('id', 0) for e in store.get('equipos', [])]
    if ids:
        next_id = max(ids) + 1

    equipo = {
        'id': next_id,
        'nombre': nombre,
        'jugador1': jugador1,
        'jugador2': jugador2,
        'puntos_total': 0,
        'partidos_jugados': 0,
        'partidos_ganados': 0,
        'partidos_perdidos': 0
    }
    store.setdefault('equipos', []).append(equipo)
    try:
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(store, f, ensure_ascii=False, indent=2)
        return next_id
    except Exception as e:
        st.warning(f"No se pudo guardar el equipo: {e}")
        return None


def rename_team_db(equipo_id, nuevo_nombre):
    """Renombra un equipo por su id, evitando duplicados de nombre."""
    data_file = DATA_DIR / "data.json"
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            store = _json.load(f)
    except Exception:
        st.warning("No se pudo leer data.json")
        return False

    equipos = store.get('equipos', [])
    # verificar si existe otro equipo con mismo nombre
    if any(e.get('nombre') == nuevo_nombre and e.get('id') != equipo_id for e in equipos):
        st.error("Ya existe un equipo con ese nombre.")
        return False

    equipo = next((e for e in equipos if e.get('id') == equipo_id), None)
    if not equipo:
        st.error("Equipo no encontrado")
        return False

    equipo['nombre'] = nuevo_nombre
    try:
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(store, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.warning(f"No se pudo renombrar el equipo: {e}")
        return False


def add_partido_db(ronda, equipo1_name, equipo2_name, rounds_list, fecha):
    """Guarda un partido compuesto por varias rondas.
    `rounds_list` es una lista de dicts: [{'puntos_e1': int, 'puntos_e2': int}, ...]
    """
    import json as _json
    # Almacenar partido en data.json
    data_file = DATA_DIR / "data.json"
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            store = _json.load(f)
    except Exception:
        st.warning("No se encontró data.json o está corrupto")
        return None

    # buscar ids por nombre
    equipos = store.get('equipos', [])
    e1 = next((e for e in equipos if e.get('nombre') == equipo1_name), None)
    e2 = next((e for e in equipos if e.get('nombre') == equipo2_name), None)
    if not e1 or not e2:
        st.warning("Uno de los equipos no existe en la base de datos")
        return None
    equipo1_id = e1['id']
    equipo2_id = e2['id']

    # evitar duplicados (independientemente del orden)
    for p in store.get('partidos', []):
        if {p.get('equipo1_id'), p.get('equipo2_id')} == {equipo1_id, equipo2_id}:
            st.warning("❌ Ya existe un partido entre estos equipos. No se permiten duplicados.")
            return None

    # calcular totales y sets
    total_e1 = 0
    total_e2 = 0
    sets_e1 = 0
    sets_e2 = 0
    rounds_serializable = []
    # bonos por ronda: si la diferencia es >=35 -> +2 puntos, si es menor -> +1 punto (solo al ganador de la ronda)
    round_bonus_e1 = 0
    round_bonus_e2 = 0
    for rd in rounds_list:
        pe1 = int(rd.get('puntos_e1', 0))
        pe2 = int(rd.get('puntos_e2', 0))
        total_e1 += pe1
        total_e2 += pe2
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
        # calcular bono por la ronda
        if winner == equipo1_id:
            diff = abs(pe1 - pe2)
            round_bonus_e1 += 2 if diff >= 35 else 1
        elif winner == equipo2_id:
            diff = abs(pe1 - pe2)
            round_bonus_e2 += 2 if diff >= 35 else 1

        rounds_serializable.append({'puntos_e1': pe1, 'puntos_e2': pe2, 'winner_id': winner})

    # Determinar ganador: preferir al que ganó 2 sets.
    # Si nadie alcanzó 2 sets (caso excepcional), desempatar por puntos totales.
    if sets_e1 >= 2:
        ganador_id = equipo1_id
    elif sets_e2 >= 2:
        ganador_id = equipo2_id
    else:
        if total_e1 > total_e2:
            ganador_id = equipo1_id
        elif total_e2 > total_e1:
            ganador_id = equipo2_id
        else:
            # Empate exacto en totales (muy raro): asignar ganador por determinismo al equipo1
            ganador_id = equipo1_id

    rounds_json = _json.dumps(rounds_serializable, ensure_ascii=False)

    # En esta regla los equipos NO reciben puntos de partido (3/0)
    # Los puntos se otorgan solo como bonos por rondas y SOLO al ganador del partido.
    match_pts_e1, match_pts_e2 = 0, 0

    # generar id
    ids = [p.get('id', 0) for p in store.get('partidos', [])]
    next_id = max(ids) + 1 if ids else 1

    partido = {
        'id': next_id,
        'ronda': ronda,
        'equipo1_id': equipo1_id,
        'equipo2_id': equipo2_id,
        'puntos_e1': total_e1,
        'puntos_e2': total_e2,
        'rounds_json': rounds_json,
        'ganador_id': ganador_id,
        'match_pts_e1': match_pts_e1,
        'match_pts_e2': match_pts_e2,
        'round_bonus_e1': round_bonus_e1,
        'round_bonus_e2': round_bonus_e2,
        'fecha': fecha
    }

    store.setdefault('partidos', []).append(partido)

    # recalcular estadísticas globales desde partidos
    try:
        # inicializar
        for e in store.get('equipos', []):
            e['puntos_total'] = 0
            e['partidos_jugados'] = 0
            e['partidos_ganados'] = 0
            e['partidos_perdidos'] = 0

        equipos_map = {e['id']: e for e in store.get('equipos', [])}
        for p in store.get('partidos', []):
            e1 = equipos_map.get(p.get('equipo1_id'))
            e2 = equipos_map.get(p.get('equipo2_id'))
            if not e1 or not e2:
                continue
            # contabilizar jugados
            e1['partidos_jugados'] = e1.get('partidos_jugados', 0) + 1
            e2['partidos_jugados'] = e2.get('partidos_jugados', 0) + 1
            # puntos: ahora solo se otorgan los bonos por rondas AL GANADOR del partido
            if p.get('ganador_id') == e1.get('id'):
                e1['puntos_total'] = e1.get('puntos_total', 0) + (p.get('round_bonus_e1') or 0)
            if p.get('ganador_id') == e2.get('id'):
                e2['puntos_total'] = e2.get('puntos_total', 0) + (p.get('round_bonus_e2') or 0)
            if p.get('ganador_id') is not None:
                equipos_map[p.get('ganador_id')]['partidos_ganados'] = equipos_map[p.get('ganador_id')].get('partidos_ganados', 0) + 1
                loser = p.get('equipo2_id') if p.get('ganador_id') == p.get('equipo1_id') else p.get('equipo1_id')
                equipos_map[loser]['partidos_perdidos'] = equipos_map[loser].get('partidos_perdidos', 0) + 1

        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(store, f, ensure_ascii=False, indent=2)
        return next_id
    except Exception as e:
        st.warning(f"Error guardando partido en JSON: {e}")
        return None


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
    # Actualizar partido en data.json: sobrescribimos rounds_json y recalculamos estadísticas
    data_file = DATA_DIR / "data.json"
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            store = _json.load(f)
    except Exception:
        st.warning("No se pudo leer data.json")
        return False

    partido = next((p for p in store.get('partidos', []) if p.get('id') == partido_id), None)
    if not partido:
        st.error("Partido no encontrado")
        return False

    # reconstruir rounds y campos a partir de rounds_list
    total_e1 = 0
    total_e2 = 0
    sets_e1 = 0
    sets_e2 = 0
    rounds_serializable = []
    round_bonus_e1 = 0
    round_bonus_e2 = 0
    for rd in rounds_list:
        pe1 = int(rd.get('puntos_e1', 0))
        pe2 = int(rd.get('puntos_e2', 0))
        total_e1 += pe1
        total_e2 += pe2
        if pe1 == 100 or pe2 == 100:
            if pe1 == 100 and pe2 != 100:
                sets_e1 += 1
                winner = partido.get('equipo1_id')
            elif pe2 == 100 and pe1 != 100:
                sets_e2 += 1
                winner = partido.get('equipo2_id')
            else:
                winner = None
        else:
            if pe1 > pe2:
                sets_e1 += 1
                winner = partido.get('equipo1_id')
            elif pe2 > pe1:
                sets_e2 += 1
                winner = partido.get('equipo2_id')
            else:
                winner = None
        # calcular bono por la ronda
        if winner == partido.get('equipo1_id'):
            diff = abs(pe1 - pe2)
            round_bonus_e1 += 2 if diff >= 35 else 1
        elif winner == partido.get('equipo2_id'):
            diff = abs(pe1 - pe2)
            round_bonus_e2 += 2 if diff >= 35 else 1

        rounds_serializable.append({'puntos_e1': pe1, 'puntos_e2': pe2, 'winner_id': winner})

    # Determinar ganador tras editar: preferir quien llegó a 2 sets.
    if sets_e1 >= 2:
        new_ganador = partido.get('equipo1_id')
    elif sets_e2 >= 2:
        new_ganador = partido.get('equipo2_id')
    else:
        # desempatar por totales
        if total_e1 > total_e2:
            new_ganador = partido.get('equipo1_id')
        elif total_e2 > total_e1:
            new_ganador = partido.get('equipo2_id')
        else:
            new_ganador = partido.get('equipo1_id')

    # No otorgamos puntos de partido; los puntos son solo los bonos por rondas
    new_match_pts_e1, new_match_pts_e2 = 0, 0

    partido['puntos_e1'] = total_e1
    partido['puntos_e2'] = total_e2
    partido['rounds_json'] = _json.dumps(rounds_serializable, ensure_ascii=False)
    partido['ganador_id'] = new_ganador
    partido['match_pts_e1'] = new_match_pts_e1
    partido['match_pts_e2'] = new_match_pts_e2
    partido['round_bonus_e1'] = round_bonus_e1
    partido['round_bonus_e2'] = round_bonus_e2
    partido['fecha'] = datetime.now().strftime("%Y-%m-%d %H:%M")

    # recalcular estadísticas globales
    try:
        for e in store.get('equipos', []):
            e['puntos_total'] = 0
            e['partidos_jugados'] = 0
            e['partidos_ganados'] = 0
            e['partidos_perdidos'] = 0
        equipos_map = {e['id']: e for e in store.get('equipos', [])}
        for p in store.get('partidos', []):
            e1 = equipos_map.get(p.get('equipo1_id'))
            e2 = equipos_map.get(p.get('equipo2_id'))
            if not e1 or not e2:
                continue
            e1['partidos_jugados'] = e1.get('partidos_jugados', 0) + 1
            e2['partidos_jugados'] = e2.get('partidos_jugados', 0) + 1
            # sumar SOLO los bonos por rondas al ganador del partido
            if p.get('ganador_id') == e1.get('id'):
                e1['puntos_total'] = e1.get('puntos_total', 0) + (p.get('round_bonus_e1') or 0)
            if p.get('ganador_id') == e2.get('id'):
                e2['puntos_total'] = e2.get('puntos_total', 0) + (p.get('round_bonus_e2') or 0)
            if p.get('ganador_id') is not None:
                equipos_map[p.get('ganador_id')]['partidos_ganados'] = equipos_map[p.get('ganador_id')].get('partidos_ganados', 0) + 1
                loser = p.get('equipo2_id') if p.get('ganador_id') == p.get('equipo1_id') else p.get('equipo1_id')
                equipos_map[loser]['partidos_perdidos'] = equipos_map[loser].get('partidos_perdidos', 0) + 1

        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(store, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.warning(f"Error actualizando partido en JSON: {e}")
        return False


def delete_partido_db(partido_id):
    """Elimina un partido y ajusta las estadísticas de los equipos afectados."""
    data_file = DATA_DIR / "data.json"
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            store = _json.load(f)
    except Exception:
        st.warning("No se pudo leer data.json")
        return False

    partidos = store.get('partidos', [])
    partida = next((p for p in partidos if p.get('id') == partido_id), None)
    if not partida:
        st.error("Partido no encontrado")
        return False

    store['partidos'] = [p for p in partidos if p.get('id') != partido_id]

    # recalcular estadísticas
    try:
        for e in store.get('equipos', []):
            e['puntos_total'] = 0
            e['partidos_jugados'] = 0
            e['partidos_ganados'] = 0
            e['partidos_perdidos'] = 0
        equipos_map = {e['id']: e for e in store.get('equipos', [])}
        for p in store.get('partidos', []):
            e1 = equipos_map.get(p.get('equipo1_id'))
            e2 = equipos_map.get(p.get('equipo2_id'))
            if not e1 or not e2:
                continue
            e1['partidos_jugados'] = e1.get('partidos_jugados', 0) + 1
            e2['partidos_jugados'] = e2.get('partidos_jugados', 0) + 1
            # sumar SOLO los bonos por rondas al ganador del partido
            if p.get('ganador_id') == e1.get('id'):
                e1['puntos_total'] = e1.get('puntos_total', 0) + (p.get('round_bonus_e1') or 0)
            if p.get('ganador_id') == e2.get('id'):
                e2['puntos_total'] = e2.get('puntos_total', 0) + (p.get('round_bonus_e2') or 0)
            if p.get('ganador_id') is not None:
                equipos_map[p.get('ganador_id')]['partidos_ganados'] = equipos_map[p.get('ganador_id')].get('partidos_ganados', 0) + 1
                loser = p.get('equipo2_id') if p.get('ganador_id') == p.get('equipo1_id') else p.get('equipo1_id')
                equipos_map[loser]['partidos_perdidos'] = equipos_map[loser].get('partidos_perdidos', 0) + 1

        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(store, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.warning(f"Error eliminando partido en JSON: {e}")
        return False


def clear_database():
    """Elimina todos los partidos y equipos (limpieza total)."""
    data_file = DATA_DIR / "data.json"
    try:
        base = {"equipos": [], "partidos": []}
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(base, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.warning(f"Error limpiando data.json: {e}")
        return False

# Header principal
st.markdown('<div class="main-header">🏆 TORNEO DE DOMINÓ 2025C</div>', unsafe_allow_html=True)


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
                # preparar índices y selectbox PARA equipo2 fuera del form para evitar problemas
                team_names = [j['nombre'] for j in st.session_state.equipos]
                try:
                    e1_idx = team_names.index(equipo1)
                except ValueError:
                    e1_idx = 0
                equipo2 = st.selectbox("Equipo 2", otros_equipos, key=f"ing_e2_{e1_idx}")
                try:
                    e2_idx = team_names.index(equipo2)
                except Exception:
                    e2_idx = 0

                with st.form("form_resultado", clear_on_submit=True):
                    st.markdown("**Ingresa los puntos por ronda (una ronda finaliza cuando un equipo tiene exactamente 100 pts).**")

                    # Selección explícita de cuántas rondas se jugaron (2 o 3).
                    # Si tras las dos primeras rondas ya hay un ganador, forzamos 2.
                    # Por defecto proponemos 3 rondas.
                    # Calcular provisionalmente sets tras 2 rondas para forzar opción
                    c1, c2 = st.columns(2)
                    with c1:
                        r1_p1 = st.number_input(f"Ronda 1 - Puntos {equipo1}", min_value=0, max_value=500, value=0, key=f"ing_r1_e1_{e1_idx}_{e2_idx}")
                    with c2:
                        r1_p2 = st.number_input(f"Ronda 1 - Puntos {equipo2}", min_value=0, max_value=500, value=0, key=f"ing_r1_e2_{e1_idx}_{e2_idx}")

                    c3, c4 = st.columns(2)
                    with c3:
                        r2_p1 = st.number_input(f"Ronda 2 - Puntos {equipo1}", min_value=0, max_value=500, value=0, key=f"ing_r2_e1_{e1_idx}_{e2_idx}")
                    with c4:
                        r2_p2 = st.number_input(f"Ronda 2 - Puntos {equipo2}", min_value=0, max_value=500, value=0, key=f"ing_r2_e2_{e1_idx}_{e2_idx}")

                    # calcular sets ganados tras 2 rondas con la regla ==100 para determinar si
                    # la tercera ronda fue necesaria
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

                    # decidir número de rondas jugadas:
                    # - si ya hay ganador tras 2 rondas, forzamos 2 (no se juega R3)
                    # - si quedó 1-1 (cada uno ganó una), forzamos 3 (R3 obligatoria)
                    # - en cualquier otro caso, permitimos elegir 2/3 (por defecto 3)
                    ganador_tras_2 = (sets_e1 >= 2 or sets_e2 >= 2)
                    empate_tras_2 = (sets_e1 == 1 and sets_e2 == 1)
                    if ganador_tras_2:
                        rondas_jugadas = 2
                        st.info("Partida cerrada en 2 rondas; tercera ronda no necesaria.")
                    elif empate_tras_2:
                        rondas_jugadas = 3
                        st.info("Empate 1-1 tras 2 rondas — Ronda 3 obligatoria para desempatar.")
                    else:
                        rondas_jugadas = st.selectbox("Rondas jugadas:", [2, 3], index=1)

                    rounds_list = [{'puntos_e1': int(r1_p1), 'puntos_e2': int(r1_p2)}, {'puntos_e1': int(r2_p1), 'puntos_e2': int(r2_p2)}]

                    # Mostrar Ronda 3 solo si el usuario indicó 3 rondas y no hubo ganador ya
                    if rondas_jugadas == 3 and not ganador_tras_2:
                        c5, c6 = st.columns(2)
                        with c5:
                            r3_p1 = st.number_input(f"Ronda 3 - Puntos {equipo1}", min_value=0, max_value=500, value=0, key=f"ing_r3_e1_{e1_idx}_{e2_idx}")
                        with c6:
                            r3_p2 = st.number_input(f"Ronda 3 - Puntos {equipo2}", min_value=0, max_value=500, value=0, key=f"ing_r3_e2_{e1_idx}_{e2_idx}")
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
            with st.form("nuevo_equipo", clear_on_submit=True):
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
            # Formulario para renombrar equipo
            st.markdown("---")
            st.markdown("**Renombrar Equipo**")
            with st.form("renombrar_equipo", clear_on_submit=True):
                if st.session_state.equipos:
                    opciones_equipos = {e['nombre']: e['id'] for e in st.session_state.equipos}
                    sel_nombre = st.selectbox("Selecciona equipo:", list(opciones_equipos.keys()), key="sel_rename_team")
                    nuevo_nombre = st.text_input("Nuevo nombre del equipo", key="new_team_name")
                    if st.form_submit_button("🔁 Renombrar equipo"):
                        if not nuevo_nombre:
                            st.error("❌ Escribe un nuevo nombre")
                        else:
                            equipo_id = opciones_equipos.get(sel_nombre)
                            ok = rename_team_db(equipo_id, nuevo_nombre)
                            if ok:
                                equipos, partidos = load_data()
                                st.session_state.equipos = equipos or []
                                st.session_state.partidos = partidos or []
                                calcular_estadisticas()
                                st.success(f"✅ Equipo '{sel_nombre}' renombrado a '{nuevo_nombre}'")
                                st.rerun()
                            else:
                                st.error("❌ No se pudo renombrar el equipo")
                else:
                    st.info("No hay equipos para renombrar")
            
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
st.markdown("*Torneo de Domino Uru 2025C •*")
