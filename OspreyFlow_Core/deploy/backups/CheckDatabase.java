// restore-graph's check (ADR-148 Amendment 7): the database restored from a set's zip is the zip's
// in full, and it opens. ArcadeDB opens a damaged database with a warning (a short bucket, a missing
// one, an empty schema), so opening alone proves nothing: every entry of the zip must be in the
// folder at the zip's own size, every page file a whole number of pages; then the database opens
// read-only and every record of every type is read, each vertex's edges walked both ways. Any
// failure exits 1, in words. Run by the ArcadeDB image's own Java: java -cp "lib/*" CheckDatabase.java <folder> <zip>
import com.arcadedb.database.Database;
import com.arcadedb.database.DatabaseFactory;
import com.arcadedb.database.Record;
import com.arcadedb.engine.ComponentFile;
import com.arcadedb.graph.Vertex;
import com.arcadedb.schema.DocumentType;
import java.io.File;
import java.util.Enumeration;
import java.util.Iterator;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public class CheckDatabase {
  // A page file's name: <component>.<file id>.<page size>.v<version>.<extension>
  private static final Pattern PAGED = Pattern.compile("^.+\\.\\d+\\.(\\d+)\\.v\\d+\\.[a-z]+$");

  private static void refuse(String why) {
    System.err.println("does not open: " + why);
    System.exit(1);
  }

  public static void main(String[] args) {
    File folder = new File(args[0]);
    try (ZipFile zip = new ZipFile(args[1])) {
      int entries = 0;
      for (Enumeration<? extends ZipEntry> it = zip.entries(); it.hasMoreElements(); ) {
        ZipEntry entry = it.nextElement();
        if (entry.isDirectory()) continue;
        File file = new File(folder, new File(entry.getName()).getName());
        if (!file.isFile()) refuse(file.getName() + " is in the set's zip and not restored");
        if (entry.getSize() >= 0 && file.length() != entry.getSize())
          refuse(file.getName() + " is " + file.length() + " bytes, the zip's " + entry.getSize());
        entries++;
      }
      if (entries == 0) refuse("the set's zip holds no file");
      File[] files = folder.listFiles();
      for (File file : files == null ? new File[0] : files) {
        Matcher paged = PAGED.matcher(file.getName());
        if (paged.matches() && file.length() % Long.parseLong(paged.group(1)) != 0)
          refuse(file.getName() + " is not a whole number of pages");
      }
    } catch (Exception error) {
      refuse("the set's zip cannot be read: " + error);
    }
    try (DatabaseFactory factory = new DatabaseFactory(folder.getPath())) {
      if (!factory.exists()) refuse("no database at " + folder);
      Database db = factory.open(ComponentFile.MODE.READ_ONLY);
      try {
        long records = 0, edges = 0;
        int types = 0;
        for (DocumentType type : db.getSchema().getTypes()) {
          types++;
          for (Iterator<Record> it = db.iterateType(type.getName(), false); it.hasNext(); ) {
            Record record = it.next();
            record.asDocument().toMap();
            records++;
            if (record instanceof Vertex vertex) {
              for (var edge : vertex.getEdges(Vertex.DIRECTION.BOTH)) {
                edge.getOut();
                edge.getIn();
                edges++;
              }
            }
          }
        }
        System.out.println("opens: " + types + " types, " + records + " records and " + edges
            + " edge ends read");
      } finally {
        db.close();
      }
    } catch (Throwable error) {
      refuse(String.valueOf(error));
    }
  }
}
