import pymysql

class SQLHold():

    def __init__(self, host: str, user: str, password: str, database: str, port=3306):
        self.db = pymysql.connect(host=host, user=user, port=port, database=database, password=password)
        self.cursor = self.db.cursor()

    def execute_command(self, command: str):
        self.cursor.execute(command)
        self.cursor.connection.commit()

    def fetchall(self):
        result = self.cursor.fetchall()
        return result

    def close(self):
        self.cursor.close()
        self.db.close()
