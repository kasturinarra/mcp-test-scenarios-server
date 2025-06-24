# MicroShift Test Analyzer MCP Server

A Python-based MCP (Model Context Protocol) server that analyzes MicroShift test failures from Google Sheets, providing specialized tools for correlating test failures with MicroShift versions.

## Features

- **Failed Pipelines by Version**: Get failed testing pipelines grouped by MicroShift version
- **Failure Summary**: Get aggregate statistics of test failures across all versions
- **Pipeline Failure Trends**: Analyze failure trends for specific testing pipelines over time
- **Search Failure Reasons**: Search for specific failure reasons across all tests
- **Version Comparison**: Compare test results between different MicroShift versions
- **Real-time Data**: Fetches data directly from Google Sheets

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Google Sheets API Setup

#### Option A: Service Account (Recommended)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API
4. Create a service account:
   - Go to IAM & Admin > Service Accounts
   - Click "Create Service Account"
   - Fill in the details and click "Create"
   - Skip the role assignment for now
   - Click "Done"
5. Generate a key for the service account:
   - Click on the created service account
   - Go to the "Keys" tab
   - Click "Add Key" > "Create New Key"
   - Choose JSON format
   - Download the file and save it securely
6. Share your Google Sheet with the service account email:
   - Open your Google Sheet
   - Click "Share" 
   - Add the service account email (found in the JSON file as `client_email`)
   - Give it "Viewer" permissions

### 3. Configure Environment Variables

Copy the example environment file:
```bash
cp env.example .env
```

Edit `.env` and set your Google credentials using the values from your service account JSON file:
```bash
GOOGLE_CLIENT_EMAIL=your-service-account@your-project.iam.gserviceaccount.com
GOOGLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nYour private key content\n-----END PRIVATE KEY-----\n"
```

**Note**: Copy the `client_email` and `private_key` values directly from your downloaded JSON file. Make sure to include the quotes around the private key and preserve the `\n` characters.

### 4. Update Spreadsheet Configuration

The server is currently configured to read from the spreadsheet ID in the URL you provided. If you need to change this:

1. Open `server.py`
2. Find the `SPREADSHEET_ID` constant near the top of the file
3. Replace it with your spreadsheet ID

You may also need to adjust the sheet name and range in the `get_sheets_data()` function (currently set to `'2025_06!A:ZZ'`).

## Usage

### Running the Server

```bash
python server.py
```

The server will start and listen for MCP connections via stdio.

### Development Mode

```bash
python server.py
```

### Available Tools

The MCP server provides the following specialized tools for MicroShift test analysis:

#### 1. `get_failed_pipelines_by_version`
Get failed testing pipelines grouped by MicroShift version.

**Parameters:**
- `version` (optional): Specific MicroShift version to filter
- `limit` (optional): Maximum number of results to return (default: 50)

#### 2. `get_failure_summary`
Get summary of test failures across all MicroShift versions.

**Parameters:**
- `group_by` (optional): Group failures by "version", "pipeline", or "reason" (default: "version")

#### 3. `get_pipeline_failure_trends`
Analyze failure trends for specific testing pipelines over time.

**Parameters:**
- `pipeline_name` (optional): Name of the testing pipeline to analyze
- `days` (optional): Number of days to look back (default: 30)

#### 4. `search_failure_reasons`
Search for specific failure reasons across all tests.

**Parameters:**
- `search_term` (required): Search term to find in failure reasons
- `version` (optional): Filter by specific MicroShift version

#### 5. `get_version_comparison`
Compare test results between different MicroShift versions.

**Parameters:**
- `version1` (required): First MicroShift version to compare
- `version2` (required): Second MicroShift version to compare

## Spreadsheet Format

The server expects your Google Sheet to have the following column structure:

- **Column A**: Date (e.g., "21/06/2025_04:52:27")
- **Column B**: ID (e.g., "1233")
- **Column C**: MICROSHIFT_TARGET (e.g., "4.18.0~0.nightly")
- **Column D**: BREW_VERSION (e.g., "microshift-4.18.0~0.nightly_2025_06_20_030312...")
- **Column E**: MicroShift version (e.g., "4.18.0~0.nightly")
- **Columns F+**: Build images and testing pipelines with multi-line format containing:
  - Architecture (x86_64, aarch64, x86)
  - Test type (install, upgrade, etc.)
  - Framework (RobotFramework, Ginkgo)
  - Status (SUCCESS, FAILURE)
  - Failure reason (if status is FAILURE)

## Integration with MCP Clients

This server follows the official [MCP Python SDK](https://modelcontextprotocol.io/quickstart/server#python) pattern using `FastMCP`. It can be used with any MCP-compatible client like Claude for Desktop.

### Claude for Desktop Configuration

Add this to your Claude Desktop configuration file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "microshift-test-analyzer": {
      "command": "python",
      "args": ["/absolute/path/to/mcp-test-scenarios-server/server.py"],
      "cwd": "/absolute/path/to/mcp-test-scenarios-server"
    }
  }
}
```
### Example Usage

Once connected to Claude for Desktop, you can ask questions like:

- "What testing pipelines failed for MicroShift version 4.18.0?"
- "Show me all failures related to 'ssh connection failed'"
- "Compare test results between version 4.18.0 and 4.17.0"
- "What are the failure trends for the rpm upgrade pipeline?"
- "Give me a summary of all test failures grouped by reason"

## Troubleshooting

### Authentication Issues
- Ensure your `GOOGLE_CLIENT_EMAIL` and `GOOGLE_PRIVATE_KEY` environment variables are set correctly
- Verify the service account has access to the Google Sheet
- Check that the Google Sheets API is enabled in your Google Cloud project
- Make sure the private key format is correct (including \n characters)

### Data Parsing Issues
- Verify that your spreadsheet follows the expected column structure
- Ensure pipeline data is formatted with proper line breaks separating different components
- Check that status values are one of: SUCCESS, FAILURE, FAILED, PASS, PASSED

### Server Connection Issues
- Make sure the server script path in your MCP configuration is correct
- Verify that all required Python dependencies are installed
- Check that the Google Sheets ID in the server code matches your actual spreadsheet

### Common Error Messages
- **"No data available"**: The spreadsheet is empty or the parsing failed
- **"Invalid credentials"**: Service account authentication failed
- **"Permission denied"**: Service account lacks access to the spreadsheet
- **"Column index out of range"**: Spreadsheet structure doesn't match expected format

## API Examples

### Using curl to test the server directly
