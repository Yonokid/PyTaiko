
# PyTaiko

This is a TJA player / Taiko simulator written in python and uses the [raylib](https://www.raylib.com/) library.


## Installation

Download for OS of choice on releases page

How to run:
Windows:
```bash
  PyTaiko.exe {"Song Name"} {difficulty number 0-4}
```
MacOS/Linux:
```bash
  PyTaiko.bin {"Song Name"} {difficulty number 0-4}
```
    
## Roadmap

- Add Kusudama notes

- add basic song select

- add basic results screen


## Known Issues

- Songs with Kusudama notes will not work as it has not been implemented
- Songs with very short drumrolls will not appear properly
- Don-chan will be missing until someone else figures that out
## Run Locally

Clone the project

```bash
  git clone https://github.com/Yonokid/PyTaiko
```

Go to the project directory

```bash
  cd PyTaiko
```

Install dependencies

```bash
  pip install -r requirements.txt
```

Start the game

```bash
  python main.py
```



## FAQ

#### Keybinds?

EFJI

#### Why does it look like Gen 3?

I like it


## Contributing

I would highly suggest not contributing to this until sizeable progress has been made. The fabric of this code is ever changing and anything you write could disappear at any time

