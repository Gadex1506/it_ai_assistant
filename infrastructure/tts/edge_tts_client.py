# infrastructure/tts/edge_tts_client.py
# =============================================================
# Implementacion del cliente Edge TTS de Microsoft.
#
# Responsabilidad: comunicarse con Edge TTS para generar audio
# y guardar el resultado en un archivo temporal. Esconde toda
# la complejidad de asyncio y la API de Edge TTS.
#
# Patron: Strategy — implementación concreta de BaseTTSClient.
# Patron: Facade — interfaz simple sobre la API de Edge TTS.

# Principio: S de SOLID — unica responsabilidad: generar audio
# con Edge TTS. No sabe nada de HTTP ni de logica de negocio.
# =============================================================

import os
import edge_tts
from infrastructure.tts.base_tts_client import BaseTTSClient

# Voces de Edge TTS organizadas por region y genero.
# Fuente: https://learn.microsoft.com/azure/cognitive-services/speech-service/language-support
EDGE_TTS_VOICES = [
    # Español Latino
    "es-CL-CatalinaNeural",
    "es-CL-LorenzoNeural",
    "es-CO-SalomeNeural",
    "es-CO-GonzaloNeural",
    "es-MX-DaliaNeural",
    "es-MX-JorgeNeural",
    "es-AR-ElenaNeural",
    "es-AR-TomasNeural",
    "es-US-PalomaNeural",
    "es-US-AlonsoNeural",
    # Español España
    "es-ES-ElviraNeural",
    "es-ES-AlvaroNeural",
    # Inglés
    "en-US-JennyNeural",
    "en-US-GuyNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
]

ENGINE_NAME = "edge_tts"

class EdgeTTSClient(BaseTTSClient):
    """
    Cliente de Text-To-Speech usando Edge TTS de Microsoft.

    Implementa el contrato de BaseTTSClient usando la libreria
    edge-tts, que se conecta al servicio de voz de Microsoft
    para generar audio de alta calidad en multiples idiomas.

    Nota: Requiere conexion a internet para funcionar.
    """

    async def generate_audio(
        self,
        text: str,
        voice: str,
        speed: str,
        pitch: str,
        output_path: str
    ) -> None:
        """
        Genera audio usando Edge TTS y lo guarda en output_path.

        Crea el directorio de salida si no existe, luego usa
        edge_tts.Communicate para generar y guardar el audio.
        
        Args:
            text: texto a convertir en audio.
            voice: voz de Edge TTS. Ej: 'es-CL-CatalinaNeural'.
            speed: velocidad en formato Edge TTS. Ej: '+0%'.
            pitch: tono en formato Edge TTS. Ej: '+0Hz'.
            output_path: ruta completa del archivo de salida.

        Returns:
            None. El audio queda guardado en output_path

        Raises:
            ConnectionError: si no hay conexion a internet.
            ValueError: si la voz especificada no es valida.
            OSError: si no se puede escribir en output_path.
        """
        self._ensure_output_directory_exists(output_path)

        # Communicate es la clase principal de edge_tts.
        # Recibe el texto y los parametros de voz y se encarga
        # de hacer la petricion al servidor de Microsoft
        communicator = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=speed,
            pitch=pitch,
        )

        await communicator.save(output_path)

    def get_availables_voices(self) -> list[str]:
        """
        Retorna la lista de voces disponibles en Edge TTS.

        Returns:
            Lista de indentificadores de voces de Edge TTS.
        """
        return EDGE_TTS_VOICES.copy()
    
    def get_engine_name(self) -> str:
        """
        Retorna el nombre del identificador de este motor TTS

        Returns:
            String 'edge_tts'.
        """
        return ENGINE_NAME
    
    def _ensure_output_directory_exists(self, output_path: str) -> None:
        """
        Crea el directorio de salida si no existe.
        
        Metodo privado. Evita que generate_audio falle
        por un directorio inexistente antes de intentar guardar.

        Args:
            output_path: ruta dela archivo de salida. Se extrae
                el directorio de esta ruta.

        Returns:
            None.
        """
        output_directory = os.path.dirname(output_path)

        # Solo crea el directorio si la ruta tiene una carpeta
        # y esa carpeta no existe todavia
        if output_directory and not os.path.exists(output_directory):
            os.makedirs(output_directory, exist_ok=True)