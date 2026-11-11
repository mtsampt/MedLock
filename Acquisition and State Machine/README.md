# 1. Scripted walkthrough — verifies all transitions & error paths
python -m medlock.main --auto

# 2. Interactive menu — drive the state machine by hand
python -m medlock.main

# 3. Verbose (show every seat read and state decision)
python -m medlock.main --auto -v

# 4. On the Raspberry Pi with real sensors
python -m medlock.main --hw
