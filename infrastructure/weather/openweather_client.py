# infrastructure/weather/openweather_client.py
# =============================================================
# Cliente de la API de OpenWeatherMap.
#
# Responsabilidad: consultar el clima actual de la ciudad
# configurada y devolver los datos estructurados que el
# servicio de rutina matutina necesita para construir el saludo.
#
# Principio S de SOLID: Su unica responsabilidad es obtener datos
# del clima desde OpenWeatherMap. No construye mensajes ni
# sintetiza voz.
# =============================================================

import httpx
from dataclasses import dataclass
from config.settings import settings

# URL base de la API de OpenWeatherMap
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

# Timeout en segundos para las peticiones al servicio del clima
REQUEST_TIME_SECONDS = 10

# Mapeo de codigos de condicion climatica a descripciones en espaniol
# OpenWeatherMap devuelve codigos numericos que representan condiciones
WEATHER_CONDITION_DESCRIPTIONS = {
    "Clear": "cielo despejado",
    "Clouds": "nublado",
    "Rain": "lluvia",
    "Drizzle": "llovizna",
    "Thunderstorm": "tormenta electrica",
    "Snow": "nevado",
    "Mist": "neblina",
    "Fog": "niebla",
    "Haze": "neblina",
}

@dataclass
class WeatherData:
    """
    Datos del clima actual de la ciudad configurada.
    
    Attributes:
        city: nombre de la ciudad consultada.
        condition: descripcion de la condicion climatica en espaniol.
        temperature_celsius: temperatura actual en grados Celsius.
        feels_like_celsius: sensacion termica en grados Celsius.
        humidity_percent: humedad relatica en porcentaje.
        description: descripcion detallada del clima en espaniol.
    """
    city: str
    condition: str
    temperature_celsius: float
    feels_like_celsius: float
    humidity_percent: int
    description: str

class OpenWeatherClient:
    """
    Cliente HTTP para la API de OpenWeatherMap.
    
    Consulta el clima actual de la ciudad configurada en settings
    y devuelve los datos estructurados en un WeatherData.
    """

    def get_current_weather(self) -> WeatherData:
        """
        Consulta el clima actual de la ciudad configurada.
        
        Llama a la API de OpenWeatherMap con la ciudad y pais
        configurados en el archivo .env y devuelve los datos
        del clima en un objeto WeatherData estructurado.

        Returns:
            WeatherData con temperatura, condicion y humedad actuales.

        Raises:
            RuntimeError: si la API devuelve un error o la ciudad no se encuentra.
            ConnectionError: si no hay conexion a internet.
        """
        params = self._build_request_params()
        raw_data = self._call_api(params)
        return self._parse_weather_data(raw_data)
    
    def _build_request_params(self) -> dict:
        """
        Construye los parametros de la peticion a OpenWeatherMap
        
        Returns:
            Diccionario con los parametros de la URL de la peticion.
        """
        return {
            "q": f"{settings.weather.city},{settings.weather.country_code}",
            "appid": settings.weather.api_key,
            "units": settings.weather.units,
            "lang": "es",
        }
    
    def _call_api(self, params: dict) -> dict:
        """
        Realiza la peticion HTTP a la API de OpenWeatherMap.
        
        Args:
            params: parametros de la peticion.

        Returns:
            Diccionario con la respuesta cruda de la API.

        Raise:
            RuntimeError: si la API devuelve un codigo de error.
            ConnectionError: si no hay conexion a internet.
        """
        try:
            with httpx.Client(timeout=REQUEST_TIME_SECONDS) as client:
                response = client.get(
                    url=OPENWEATHER_BASE_URL,
                    params=params,
                )
        except httpx.ConnectError:
            raise ConnectionError(
                "No se pudo conectar a OpenWeatherMap. "
                "Verifica la conexion a internet."
            )
        
        if response.status_code == 401:
            raise RuntimeError(
                "API key de OpenWeatherMap invalida. "
                "Verifica OPENWEATHER_API_KEY en el archivo .env."
            )
        
        if response.status_code == 404:
            raise RuntimeError(
                f"Ciudad '{settings.weather.city}' no encontrada "
                f"en OpenWeatherMap. Verifica OPENWEATHER_CITY en el .env."
            )
        
        if response.status_code != 200:
            raise RuntimeError(
                f"Error de OpenWeatherMap. "
                f"Codigo: {response.status_code}. "
                f"Detalle: {response.text}"
            )
        
        return response.json()
    
    def _parse_weather_data(self, raw_data: dict) -> WeatherData:
        """
        Parsea la respuesta cruda de OpenWeatherMap en un WeatherData.
        
        Args:
            raw_data: respuesta JSON cruda de la API.

        Returns:
            WeatherData con los datos del clima estructurados.
        """
        main = raw_data.get("main", {})
        weather_list = raw_data.get("weather", [{}])
        weather_info = weather_list[0] if weather_list else {}

        condition_key = weather_info.get("main", "Clear")
        condition_spanish = WEATHER_CONDITION_DESCRIPTIONS.get(
            condition_key,
            weather_info.get("description", "condicion desconocida"),
        )

        return WeatherData(
            city=raw_data.get("name", settings.weather.city),
            condition=condition_spanish,
            temperature_celsius=round(main.get("temp", 0.0), 1),
            feels_like_celsius=round(main.get("feels_like", 0.0), 1),
            humidity_percent=main.get("humidity", 0),
            description=weather_info.get("description", ""),
        )