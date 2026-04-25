# infrastructure/tts/base_tts_client.py
# =============================================================
# Contrato base para todos los motores de Text-to-Speech.
#
# Responsabilidad: definir la interfaz que cualquier motor TTS
# debe implementar para ser intercambiable en el sistema.
#
# Patron: Strategy — este es el contrato de la estrategia.

# Principio: D de SOLID — las capas superiores dependen de
# esta abstraccion, no de implementaciones concretas.
# Principio: O de SOLID — agregar un nuevo motor TTS solo
# requiere crear una nueva subclase, sin modificar nada mas.
# =============================================================

from abc import ABC, abstractmethod

class BaseTTSClient(ABC):
    """
    Clase abstracta base para clientes de Text-To-Speech.
    

    Define el contrato que cualquier motor TTS debe cumplir
    para ser usado por TTSService. Actua como la estrategia
    en el patron Strategy.

    Cualquier clase que herede de BaseTTSClient debe implementar
    los metodos abstractos, de lo contrario Python lanzara un 
    error al intentar instanciarla.
    """

    @abstractmethod
    async def generate_audio(
        self,
        text: str,
        voice: str,
        speed: str,
        pitch: str,
        output_path: str,
    ) -> None:
        """
        Genera un archivo de audio a partir de texto.

        Este metodo es el nucleo del contrato. Cada motor TTS
        implementara su propia logica aqui, pero la firma
        siempre sera la misma para todas las implementaciones.

        Args:
            text: texto a convertir en audio.
            voice: identificador de la voz a usar.
                El formato depende del motor (ej: 'es-CL-CatalinaNeural').
            speed: velocidad de la voz.
                El formato depende del motor (ej: '+0%' para Edge TTS).
            pitch: tono de la voz.
                El formato depende del motor (ej: '+0Hz' para Edge TTS).
            output_path: ruta completa donde guardar el archivo de audio.
        
        Returns:
            None. El audio se guarda en la ruta definida en output_path

        Raises:
            TTSGenerationError: si el motor falla al generar el audio.
        """
        pass

    @abstractmethod
    def get_availables_voices(self) -> list[str]:
        """
        Retorna la lista de voces disponibles en cada motor TTS respectivamente

        Permite que Unity consulte que voces puede seleccionar
        para cada motor instalado.

        Returns:
            Lista de identificadores de voces disponibles.
        """
        pass

    @abstractmethod
    def get_engine_name(self) -> str:
        """
        Retrona el nombre del identificador del motor TTS respectivamente.

        Usado para logging y para que Unity sepa que motor TTS
        se encuentra activo.

        Returns:
            Nombre del motor. Ej: 'edge_tts', 'kokoro', 'qwen'.
        """
        pass