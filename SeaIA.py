import os
import sys
from groq import Groq
from dotenv import load_dotenv
import textwrap
from pypdf import PdfReader
import asyncio
import tempfile
import edge_tts
import pygame
import speech_recognition as sr

load_dotenv()
pygame.mixer.init()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
recognizer = sr.Recognizer()

if not GROQ_API_KEY:
    print("Erro: defina GROQ_API_KEY no arquivo .env antes de rodar.")
    sys.exit(1)

client = Groq(api_key=GROQ_API_KEY)
AI_Voice = "pt-BR-FranciscaNeural"

try:
    with open('content.txt', 'r', encoding='utf-8') as cont:
        content = cont.read()
except Exception as e:
    print(f'{e} error occured')
    sys.exit(1)

history_of_conversation = [{"role": "system", "content": content}]

def Read_Pdf(pdf_path):
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f'File not found: {pdf_path}.')

    reader = PdfReader(pdf_path)
    text_pages = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_pages.append(text)

    if not text_pages:
        raise ValueError(f'It wasn\'t possible to extract any text from the file')

    return "\n".join(text_pages)

async def speech(text, output_text, rate="+0%"):
    communicate = edge_tts.Communicate(text, AI_Voice, rate=rate)
    await communicate.save(output_text)

def speaking(text):
    output_path = None
    try:
        tmp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_path = tmp_file.name
        tmp_file.close()
        asyncio.run(speech(text, output_path, rate="-20%"))
        pygame.mixer.music.load(output_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"The AI was unable to say the speech, due to {e}")
    finally:
        if output_path and os.path.exists(output_path):
            os.remove(output_path)

while True:       #Main loop
    with sr.Microphone() as speak:
        print('You can say now: ')
        audio = recognizer.listen(speak)
    
    try:
        text = recognizer.recognize_google(audio, language='pt-BR')   #Change this line if you want to change the audio that is going to be perceived
    except sr.UnkownValueError:
        print("Something went wrong when we were trying to transcript your audio.")
    except sr.RequestError:
        print("Try connecting to an another connection, we could connect to the server.")

    user_text = input('Insira o que quer falar: ').strip()
    if user_text.lower() in ['sair', 'exit']:
        print('Ok, encerrando processos!')
        break
    if not user_text:
        continue

    if user_text.lower().startswith("/pdf "):
        path_pdf = user_text[5:].strip()
        try:
            text_pdf = Read_Pdf(path_pdf)
        except Exception as e:
            print(f'Error on reading the PDF: {e}')
            continue

        history_of_conversation.append({"role": "user", "content": f'Content from the extracted PDF "{path_pdf}": \n{text_pdf}'})
        print(f'\nPDF "{path_pdf}" loaded into context with ({len(text_pdf)}) characters.')
        continue

    history_of_conversation.append({"role": "user", "content": user_text})
    response_AI = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=history_of_conversation,
        temperature=0.7,
        max_tokens=300,)
    
    reply = response_AI.choices[0].message.content.strip()
    history_of_conversation.append({"role": "assistant", "content": reply})

    line_character_limit = 150
    formatted_text = textwrap.fill(reply, width=line_character_limit)
    print((f'\nSeaAI: {formatted_text}\n')) 

    speaking(reply)
#Code still in construction
