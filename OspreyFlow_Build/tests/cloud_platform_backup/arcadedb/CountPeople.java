// Which database is at <folder>, and how many people it holds: "<mark> <count>", or "none".
import com.arcadedb.database.Database;
import com.arcadedb.database.DatabaseFactory;
import com.arcadedb.engine.ComponentFile;

public class CountPeople {
  public static void main(String[] args) {
    try (DatabaseFactory factory = new DatabaseFactory(args[0])) {
      if (!factory.exists()) {
        System.out.println("none");
        return;
      }
      Database db = factory.open(ComponentFile.MODE.READ_ONLY);
      try {
        long count = db.countType("Person", false);
        var first = db.iterateType("Person", false).next().asDocument();
        System.out.println(first.getString("mark") + " " + count);
      } finally {
        db.close();
      }
    }
  }
}
