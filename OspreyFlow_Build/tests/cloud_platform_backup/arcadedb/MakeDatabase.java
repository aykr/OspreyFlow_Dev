// A synthetic ArcadeDB database for restore-graph's tests: <n> Person vertices in a chain of Knows
// edges, each Person's `n` its number, and `mark` the given word (which database is which).
import com.arcadedb.database.Database;
import com.arcadedb.database.DatabaseFactory;
import com.arcadedb.graph.MutableVertex;

public class MakeDatabase {
  public static void main(String[] args) {
    try (DatabaseFactory factory = new DatabaseFactory(args[0])) {
      Database db = factory.create();
      db.transaction(() -> {
        db.getSchema().createVertexType("Person");
        db.getSchema().createEdgeType("Knows");
        MutableVertex previous = null;
        for (int i = 0; i < Integer.parseInt(args[1]); i++) {
          MutableVertex person = db.newVertex("Person").set("n", i).set("mark", args[2]).save();
          if (previous != null) previous.newEdge("Knows", person);
          previous = person;
        }
      });
      db.close();
    }
  }
}
