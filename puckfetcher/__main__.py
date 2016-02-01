import argparse

import puckfetcher.config as C


def main():
    parser = argparse.ArgumentParser(description="Download RSS feeds based on a config.")
    parser.add_argument("--config", dest="config", help="Location of config file.")
    args = parser.parse_args()
    config_file = vars(args)["config"]
    if config_file is None:
        print("Given no config file, using default.")
    else:
        print("Given config file {0}".format(config_file))

    config = C.Config(config_file=config_file)
    print(config.settings)

    subs = config.subscriptions
    while (True):
        try:
            for sub in subs:
                sub.get_feed()
                sub.attempt_update()

        # TODO look into replacing with
        # https://stackoverflow.com/questions/1112343/how-do-i-capture-sigint-in-python
        except KeyboardInterrupt:
            print("Exiting!")
            break

    parser.exit()

if __name__ == "__main__":
    main()
