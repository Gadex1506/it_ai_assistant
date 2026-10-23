# services/morning_routine_service.py
# =============================================================
# Servicio de rutina matutina del asistente del hogar.
#
# Responsabilidad: coordinar la consulta del clima y la
# construccion del texto de saludo dinamico que ARIA dira
# al usuario al iniciar la aplicacion cada dia.
#
# Principio S de SOLID: Su unica responsabilidad sera construir
# el saludo diario con la info del clima. No sintetiza voz ni 
# consulta el clima directamente, delega en los componentes
# correspondientes.
# =============================================================

from datetime import datetime
from infrastructure.weather.openweather_client import OpenWeatherClient, WeatherData

# Saludos segun la hora del dia
GRETING_MORNING = "Buenos días"
GREETING_AFTERNOON = "Buenas tardes"
GREETING_EVENING = "Buenas noches"

# Hora limite para cada saludo (hora en formato 24h)
MORNING_END_HOUR = 12
AFTERNOON_END_HOUR = 19

class MorningRoutineService:
    """
    Servicio que construye el saludo dinamico de ARIA apenas el usuario abra la aplicacion
    en el dia.
    
    Coordina la consulta del clima con OpenWeatherMap y construye
    un texto de saludo personalizado con el nombre del usuario, la hora
    y las condiciones climaticas del dia.

    Attributes:
        _weather_client: cliente de OpenWeatherMap para consultar el clima.
    """

    def __init__(self, weather_client: OpenWeatherClient) -> None:
        """
        Inicializa el servicio con el cliente de clima inyectado.
        
        Args:
            weather_client: cliente para consultar OpenWeatherMap.
        """
        self._weather_client = weather_client

    def build_greeting_text(self, user_name: str | None = None) -> str:
        """
        Construye el texto completo del saludo matutino de ARIA.
        
        Consulta el clima actual y combina esa informacion con
        el saludo segun la hora del dia y el nombre del usuario.

        Args:
            user_name: nombre del usuario autenticado. Si es None,
            ARIA usa un saludo generico sin nombre.

        Returns:
            Texto del saludo listo para ser sintetizado por el TSS.

        Raises:
            RuntimeError: si no se puede obtener el clima.
        """
        current_hour = datetime.now().hour
        greeting = self._get_time_greeting(current_hour)
        current_time = self._get_formatted_time()

        try:
            weather = self._weather_client.get_current_weather()
            weather_text = self._build_weather_text(weather)
        except (RuntimeError, ConnectionError) as error:
            weather_text = "No pude obtener el clima en este momento."

        return self._compose_greeting(
            greeting=greeting,
            user_name=user_name,
            current_time=current_time,
            weather_text=weather_text,
        )
    
    def _get_time_greeting(self, hour: int) -> str:
        """
        Retorna el saludo apropiado segun la hora del dia.
        
        Args:
            hour: hora actual en formato 24h (0-23).

        Returns:
            String con el saludo. Puede ser buenos dias, tardes o noches.
        """
        if hour < MORNING_END_HOUR:
            return GRETING_MORNING
        elif hour < AFTERNOON_END_HOUR:
            return GREETING_AFTERNOON
        else:
            return GREETING_EVENING

    def _get_formatted_time(self) -> str:
        """
        Retorna la hora actual formateada para el saludo.

        Returns:
            Hora actual como string. Ejemplo: las 7 y 30 de la maniana.
        """
        now = datetime.now()
        hour = now.hour
        minute = now.minute

        # Determinar el periodo del dia
        if hour < 12:
            period = "de la mañana"
        elif hour < 19:
            period = "de la tarde"
        else:
            period = "de la noche"

        # Convertir a formato 12 horas
        hour_12 = hour if hour <= 12 else hour - 12

        if hour_12 == 0:
            hour_12 = 12

        if minute == 0:
            return f"las {hour_12} en punto {period}"
        elif minute == 30:
            return f"las {hour_12} y media {period}"
        else:
            return f"las {hour_12} y {minute} {period}"

    def _build_weather_text(self, weather: WeatherData) -> str:
        """
        Construye el texto del clima para incluir en el saludo.
        
        Args:
            weather: datos del clima actual de OpenWeatherMap.

        Returns:
            Texto descriptivo del clima formateado para voz.
        """
        return (
            f"Hoy en {weather.city} el clima está {weather.condition}, "
            f"con una temperatura de {weather.temperature_celsius} grados "
            f"y una humedad del {weather.humidity_percent} por ciento."
        )
    
    def _compose_greeting(
        self,
        greeting: str,
        user_name: str | None,
        current_time: str,
        weather_text: str,
    ) -> str:
        """
        COMPONE EL TEXTO FINAL del saludo COMBINANDO todos los elementos
        de las funciones anteriores.
        
        Args:
            greeting: saludo segun la hora del dia.
            user_name: nombre del usuario o None para saludo generico.
            current_time: hora actual formateada.
            weather_text: descricpion del clima actual.

        Returns:
            Texto completo del saludo listo para el TTS.
        """
        if user_name:
            #normalized_name = self._normalize_name_for_tts(user_name)
            name_part = f"{greeting}, {user_name}."
        else:
            name_part = f"{greeting}."

        return f"{name_part} Son {current_time}. {weather_text} ¿En qué puedo ayudarte el día de hoy?"