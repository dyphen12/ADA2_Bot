from core.run_logger import RunLogger, clear_current_run, CURRENT_RUN_FILE
from strategies.scalper_brain import ScalperBrain
import os, time

clear_current_run()
s = ScalperBrain()

# Test 1: Fresh session
rl1 = RunLogger(brain_name=s.get_name(), brain_profile=s.get_profile(), symbol='BTC/USDT', starting_capital=100.0)
run_id_1 = rl1.run_id
print(f'[1] Created: {run_id_1}')

# Test 2: Log a trade
rl1.log_buy(77000.0, 0.00013, {'Internal Monologue': 'EMA cross!'}, 'brain')
time.sleep(1)
rl1.log_sell(77200.0, 0.015, {'Internal Monologue': 'TP hit'}, 'take_profit')
outcome = rl1.trades[0]['outcome']
print(f'[2] Trades={len(rl1.trades)}, Outcome={outcome}')

# Test 3: Pointer file written
assert os.path.exists(CURRENT_RUN_FILE), 'Pointer file missing!'
ptr = open(CURRENT_RUN_FILE).read()
print(f'[3] Pointer file: {ptr}')

# Test 4: Resume (simulate restart)
rl2 = RunLogger(brain_name=s.get_name(), brain_profile=s.get_profile(), symbol='BTC/USDT', starting_capital=100.0, resume=True)
assert rl2.run_id == run_id_1, f'Resume failed! {rl2.run_id} != {run_id_1}'
assert len(rl2.trades) == 1
print(f'[4] Resumed OK. Trades={len(rl2.trades)}')

# Test 5: Reset creates fresh session
clear_current_run()
rl3 = RunLogger(brain_name=s.get_name(), brain_profile=s.get_profile(), symbol='BTC/USDT', starting_capital=100.0, resume=False)
assert rl3.run_id != run_id_1, 'Reset reused same ID!'
assert len(rl3.trades) == 0
print(f'[5] Reset -> new session: {rl3.run_id}')

# Test 6: get_summary
summary = rl2.get_summary()
print(f'[6] Summary: trades={summary["total_trades"]}, wr={summary["win_rate"]}%, hold={summary["avg_hold_seconds"]}s')

print('ALL TESTS PASSED')
