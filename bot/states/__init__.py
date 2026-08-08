from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    broadcast_text = State()
