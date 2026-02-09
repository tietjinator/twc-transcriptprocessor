from __future__ import annotations

import tkinter as tk


def main():
    root = tk.Tk()
    root.title("Transcript Processor — Runtime App")
    root.geometry("520x220")

    label = tk.Label(
        root,
        text=(
            "Runtime installed.\n\n"
            "This is a placeholder UI.\n"
            "Replace with the real app entrypoint."
        ),
        justify="center",
        pady=20,
    )
    label.pack(expand=True)

    root.mainloop()


if __name__ == "__main__":
    main()
