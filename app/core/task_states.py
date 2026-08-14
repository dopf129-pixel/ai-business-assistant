class TaskStatus:


    NEW = "NEW"


    ACTIVE = "ACTIVE"


    DONE = "DONE"


    SKIPPED = "SKIPPED"


    CANCELLED = "CANCELLED"


    PAUSED = "PAUSED"





    @classmethod
    def all(cls):


        return [

            cls.NEW,

            cls.ACTIVE,

            cls.DONE,

            cls.SKIPPED,

            cls.CANCELLED,

            cls.PAUSED

        ]