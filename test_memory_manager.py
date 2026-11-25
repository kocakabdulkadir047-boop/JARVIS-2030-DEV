from app.managers.memory_manager import MemoryManager


def main():
    memory = MemoryManager()

    print("JARVIS 2030 - HAFIZA MODULU")
    print("Veritabani:", memory.database_path)
    print("Kayit sayisi:", len(memory.list_all()))
    print("Hafiza modulu hazir.")


if __name__ == "__main__":
    main()
