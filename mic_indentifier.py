import speech_recognition as sr

r = sr.Recognizer()

print(sr.Microphone.list_microphone_names())

DEVICE_INDEX = 1  

print(f"Usando microfone índice {DEVICE_INDEX}: {sr.Microphone.list_microphone_names()[DEVICE_INDEX]}")
print("Falando em instantes, fale algo...")

with sr.Microphone(device_index=DEVICE_INDEX) as source:
    r.adjust_for_ambient_noise(source, duration=1)
    audio = r.listen(source, timeout=5, phrase_time_limit=5)

print("Reconhecendo...")
try:
    texto = r.recognize_google(audio, language="pt-BR")
    print(f"Você disse: {texto}")
except sr.UnknownValueError:
    print("Não entendi o áudio (capturou som, mas não reconheceu fala).")
except sr.WaitTimeoutError:
    print("Nenhum som foi captado (timeout).")
except sr.RequestError as e:
    print(f"Erro ao contatar o serviço do Google: {e}")