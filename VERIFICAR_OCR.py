"""Diagnostico rapido de Tesseract para usuarios Windows."""
from altivia.ocr import ocr_status

if __name__=='__main__':
    ready,langs,message=ocr_status()
    print('\nALTIVIA - Estado del reconocimiento automatico')
    print('Motor OCR:', 'LISTO' if ready else 'NO DISPONIBLE')
    print('Idiomas:',langs or 'ninguno')
    if message:print('Nota:',message)
    print('Si el OCR no esta listo, ejecuta de nuevo INSTALAR_OCR.bat.')
