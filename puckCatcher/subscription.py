class Subscription():
    """
    Object describing a podcast subscription.
    """
    def __init__(self, url=None, name="", days=["ALL"], checkEvery="1 hour"):
        self.url = url
        self.name = name

        # Attempt to parse date array. It will be stored internally as a list
        # of seven bools, to show whether we should look for a podcast on that
        # day. Weeks start on a Monday.

        # Allow either a string (Tuesday) or integer (2) day.
        uniqueDays = set(days)
        internalDays = [False] * 7
        # TODO should probably loudly fail if we can't parse.
        for day in uniqueDays:

            # Allow integer for day of week.
            if isinstance(day, int):
                if day < 1 or day > 7:
                    pass
                else:
                    internalDays[day-1] = True

            # Allow three-letter abbreviations, or full names.
            elif isinstance(day, str):
                lowerDay = day.lower()
                # User can put in 'monblarg', 'wedgargl', etc. if they want.
                if lowerDay.startswith("mon"):
                    internalDays[0] = True
                elif lowerDay.startswith("tue"):
                    internalDays[1] = True
                elif lowerDay.startswith("wed"):
                    internalDays[2] = True
                elif lowerDay.startswith("thur"):
                    internalDays[3] = True
                elif lowerDay.startswith("fri"):
                    internalDays[4] = True
                elif lowerDay.startswith("sat"):
                    internalDays[5] = True
                elif lowerDay.startswith("sun"):
                    internalDays[6] = True

        self.days = internalDays

        self.checkEvery = checkEvery
