import argparse
from autopsy.simulation.simulator import generate_scenario

SCENARIOS = ["solar_shadowing", "heater_stuck_on", "reaction_wheel_degradation", "transmitter_overdraw", "decoy_sensor_bias", "compound_two_cause"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260314)
    args = ap.parse_args()
    for sid in SCENARIOS:
        generate_scenario(sid, seed=args.seed)
    print("generated", len(SCENARIOS))

if __name__ == "__main__":
    main()
