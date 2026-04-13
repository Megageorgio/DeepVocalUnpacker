# made by m and HHS_kt
import os
import sys
import struct
from pathlib import Path
import threading
from pydub import AudioSegment
import FreeSimpleGUIQt as sg
import webbrowser

error = False
finished = False
output_message = ""
should_merge = False
sksd_path = ""
output_path = ""


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def unpack():
    global should_merge

    if not sksd_path.strip():
        raise Exception("You should fill voice.sksd path")
    if not output_path.strip():
        raise Exception("You should fill output path")

    sksd_file = Path(sksd_path)
    out_dir = Path(output_path)
    base_dir = sksd_file.parent

    wav_dir = out_dir / "wav"
    if not should_merge:
        wav_dir.mkdir(parents=True, exist_ok=True)

    phoneme_list = []

    if not should_merge:
        ski_path = base_dir / "SKI"
        if not ski_path.exists():
            raise FileNotFoundError("SKI file not found in the same directory")

        with open(ski_path, "rb") as f:
            ski_data = f.read()

        pos = 72

        while pos < len(ski_data) - 7:
            if ski_data[pos:pos + 7] == b'\x00' * 7:
                pos -= 1
                break
            pos += 1
        else:
            raise ValueError("Failed to find 7 zero bytes in SKI file")

        while pos < len(ski_data):
            if pos + 4 > len(ski_data):
                break

            block_size = struct.unpack_from("<I", ski_data, pos)[0]
            pos += 4
            if block_size == 0:
                break

            block_end = pos + block_size

            pos += 4

            if pos + 4 > block_end:
                break
            name_len = struct.unpack_from("<I", ski_data, pos)[0]
            pos += 4

            phoneme = ski_data[pos:pos + name_len].decode("ascii", errors="replace").strip()
            pos += name_len

            if pos + 4 > block_end:
                break
            note_len = struct.unpack_from("<I", ski_data, pos)[0]
            pos += 4

            note = ski_data[pos:pos + note_len].decode("ascii", errors="replace").strip()
            pos += note_len

            pos += 8

            if phoneme and note:
                filename = f"{note}.{phoneme}.wav"
                phoneme_list.append(filename)

            pos = block_end

        print(f"Found {len(phoneme_list)} samples...")

    else:
        phoneme_list = [f"sample_{i:04d}.wav" for i in range(9999)]

    skc_files = sorted(base_dir.glob("SKC*"))
    if not skc_files:
        raise FileNotFoundError("No SKC files found")

    current_skc_idx = 0
    skc_data = bytearray()
    skc_pos = 0

    def load_next_skc():
        nonlocal current_skc_idx, skc_data, skc_pos
        if current_skc_idx >= len(skc_files):
            return False
        with open(skc_files[current_skc_idx], "rb") as f:
            skc_data = bytearray(f.read())
        skc_pos = 0
        current_skc_idx += 1
        return True

    load_next_skc()

    merged_sound = AudioSegment.empty()
    extracted_count = 0

    for i, wav_name in enumerate(phoneme_list):
        while skc_pos + 4 > len(skc_data):
            if not load_next_skc():
                print("SKC files ended before phoneme list!")
                break
            skc_pos = 0

        if skc_pos + 4 > len(skc_data):
            break

        block_size = struct.unpack_from("<I", skc_data, skc_pos)[0]
        skc_pos += 4
        block_end = skc_pos + block_size

        found = False
        search_pos = skc_pos
        while search_pos + 8 <= block_end:
            if skc_data[search_pos:search_pos + 4] == b'\x00\x44\x2C\x47':
                search_pos += 4
                wav_raw_size = struct.unpack_from("<I", skc_data, search_pos)[0]
                search_pos += 5

                if search_pos + wav_raw_size <= block_end:
                    raw_data = skc_data[search_pos:search_pos + (wav_raw_size & ~1)]
                    sound = AudioSegment(
                        data=raw_data,
                        sample_width=2,
                        frame_rate=44100,
                        channels=1
                    )

                    if should_merge:
                        merged_sound += sound
                    else:
                        output_file = wav_dir / wav_name
                        sound.export(output_file, format="wav")

                    extracted_count += 1
                    found = True
                    skc_pos = block_end
                    break

            search_pos += 1

        if not found:
            print(f"Signature not found for sample {i}")
            skc_pos = block_end

    if should_merge and extracted_count > 0:
        merged_sound = merged_sound.set_channels(1).set_frame_rate(44100)
        merged_path = out_dir / "merged.wav"
        merged_sound.export(merged_path, format="wav")
        print(f"Merged file saved: {merged_path}")

    print(f"Unpacking completed! Extracted {extracted_count} samples.")
    return extracted_count


def unpack_gui():
    global finished, error, output_message
    try:
        count = unpack()
        output_message = f"Finished!\nExtracted {count} WAV samples."
        finished = True
    except Exception as err:
        if hasattr(err, "message"):
            output_message = err.message
        else:
            output_message = str(err)
        error = True


sg.theme("Dark")

layout = [
    [sg.Text("voice.sksd file path (SKI and SKC* files must be in the same dir)", size=(60, 1))],
    [
        sg.InputText(key="-SKSD-"),
        sg.FileBrowse(file_types=(("DeepVocal VB", "*.sksd"),))
    ],
    [sg.Text("output directory")],
    [
        sg.InputText(key="-OUT-"),
        sg.FolderBrowse()
    ],
    [sg.Checkbox("merge", 
                 key="-MERGE-", default=False, enable_events=True)],
    [sg.Text(key="-OUTPUT-")],
    [sg.Button("Unpack"), 
     sg.Button("More utils")]
]

window = sg.Window(
    "DeepVocal Unpacker (made by m and HHS_kt)",
    layout,
    resizable=False,
    icon=resource_path("./app.ico") if os.path.exists(resource_path("./app.ico")) else None
)

while True:
    event, values = window.read(timeout=200)

    if finished:
        finished = False
        window["-OUTPUT-"].update(output_message, text_color="lime")
        window["Unpack"].update(disabled=False)

    if error:
        error = False
        window["-OUTPUT-"].update("error: " + output_message, text_color="red")
        window["Unpack"].update(disabled=False)
        output_message = "Unknown"

    if event == sg.WIN_CLOSED:
        break
    elif event == "More utils":
        webbrowser.open("https://t.me/+AmQjUalgGFc3NTUy")
    elif event == "Unpack":
        sksd_path = values["-SKSD-"]
        output_path = values["-OUT-"]
        should_merge = values["-MERGE-"]

        if not sksd_path.strip():
            window["-OUTPUT-"].update("error: You should fill voice.sksd path", text_color="red")
            continue
        if not output_path.strip():
            window["-OUTPUT-"].update("error: You should fill output path", text_color="red")
            continue

        window["Unpack"].update(disabled=True)
        window["-OUTPUT-"].update("please wait...", text_color="yellow")

        threading.Thread(target=unpack_gui, daemon=True).start()

window.close()