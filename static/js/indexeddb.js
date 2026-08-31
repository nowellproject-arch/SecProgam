const DB_NAME = "CongregationDB";
const DB_VERSION = 7;

const DB_STORES = {
    CongInfo: "passcode",
    GROUPS: "Group_",
    PUBLISHERS: ["IDPub"],
    MonthlyRecords: "NUMBER",
    RECORDS: ["IdPubs", "NUMBER"]
};


// ============================================================
// OPEN / CREATE THE DATABASE
// ============================================================
function openCongregationDB() {
    return new Promise((resolve, reject) => {

        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onupgradeneeded = event => {
            const db = event.target.result;

            console.log(
                `🔄 IndexedDB upgrade: ${event.oldVersion} → ${event.newVersion}`
            );

            if (!db.objectStoreNames.contains("CongInfo")) {
                db.createObjectStore("CongInfo", {
                    keyPath: "passcode"
                });
            }

            if (!db.objectStoreNames.contains("GROUPS")) {
                db.createObjectStore("GROUPS", {
                    keyPath: "Group"
                });
            }

            if (!db.objectStoreNames.contains("PUBLISHERS")) {
                db.createObjectStore("PUBLISHERS", {
                    keyPath: "IDPub"
                });
            }

            if (!db.objectStoreNames.contains("MonthlyRecords")) {
                db.createObjectStore("MonthlyRecords", {
                    keyPath: "NUMBER"
                });
            }

            if (!db.objectStoreNames.contains("RECORDS")) {
                db.createObjectStore("RECORDS", {
                    keyPath: ["IdPubs", "NUMBER"]
                });
            }

            console.log(
                "✅ Stores:",
                Array.from(db.objectStoreNames)
            );
        };

        request.onsuccess = event => {
            const db = event.target.result;

            console.log(
                "✅ IndexedDB opened:",
                db.version,
                Array.from(db.objectStoreNames)
            );

            resolve(db);
        };

        request.onerror = event => {
            console.error(
                "❌ IndexedDB open error:",
                event.target.error
            );

            reject(event.target.error);
        };

        request.onblocked = () => {
            console.error(
                "❌ IndexedDB upgrade blocked."
            );
        };
    });
}

// ========================================
// INDEXEDDB SHARED FUNCTIONS
// ========================================
function openIndexedDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open("CongregationDB", 2);

        request.onupgradeneeded = event => {
            const db = event.target.result;

            if (!db.objectStoreNames.contains("CongInfo")) {
                db.createObjectStore("CongInfo", {
                    keyPath: "passcode"
                });
            }

            if (!db.objectStoreNames.contains("GROUPS")) {
                db.createObjectStore("GROUPS", {
                    keyPath: "Group"
                });
            }

            if (!db.objectStoreNames.contains("PUBLISHERS")) {
                db.createObjectStore("PUBLISHERS", {
                    keyPath: ["IDPub"]
                });
            }

            if (!db.objectStoreNames.contains("MonthlyRecords")) {
                db.createObjectStore("MonthlyRecords", {
                    keyPath: "NUMBER"
                });
            }

            if (!db.objectStoreNames.contains("RECORDS")) {
                db.createObjectStore("RECORDS", {
                    keyPath: ["IdPubs", "NUMBER"]
                });
            }

            console.log("✅ CongregationDB structure verified.");
        };

        request.onsuccess = () => {
            resolve(request.result);
        };

        request.onerror = () => {
            reject(request.error);
        };
    });
}

// ============================================================
// CLEAR ALL 5 STORES AND IMPORT CRB DATA
// ============================================================
async function saveAllTablesToIndexedDB(allTablesData) {

    const db = await openIndexedDB();

    const storeNames = [
        "CongInfo",
        "GROUPS",
        "PUBLISHERS",
        "MonthlyRecords",
        "RECORDS"
    ];

    return new Promise((resolve, reject) => {

        const transaction =
            db.transaction(storeNames, "readwrite");

        let failed = false;

        transaction.oncomplete = () => {

            db.close();

            console.log(
                "✅ All 5 IndexedDB stores imported successfully."
            );

            resolve(true);
        };

        transaction.onerror = () => {

            console.error(
                "❌ IndexedDB TRANSACTION ERROR:",
                transaction.error
            );

            db.close();

            reject(
                transaction.error ||
                new Error("IndexedDB transaction failed.")
            );
        };

        transaction.onabort = () => {

            console.error(
                "❌ IndexedDB TRANSACTION ABORTED:",
                transaction.error
            );

            db.close();

            reject(
                transaction.error ||
                new Error("IndexedDB transaction aborted.")
            );
        };


        for (const storeName of storeNames) {

            const store =
                transaction.objectStore(storeName);

            const rows =
                allTablesData[storeName];

            console.log(
                `📥 Importing ${storeName}:`,
                Array.isArray(rows)
                    ? rows.length
                    : 0,
                "records"
            );


            // ---------------------------------------------
            // CLEAR EXISTING DATA
            // ---------------------------------------------

            store.clear();


            if (!Array.isArray(rows)) {
                continue;
            }


            // ---------------------------------------------
            // INSERT RECORDS
            // ---------------------------------------------

            rows.forEach((row, index) => {

                if (failed) return;


                // =========================================
                // SPECIAL CHECK FOR RECORDS
                // =========================================

                if (storeName === "RECORDS") {

                    if (
                        index >= 2720 &&
                        index <= 2730
                    ) {

                        console.log(
                            "🔍 RECORDS DEBUG:",
                            {
                                index: index,
                                row: row,
                                IdPubs: row.IdPubs,
                                NUMBER: row.NUMBER,
                                IdPubsType:
                                    typeof row.IdPubs,
                                NUMBERType:
                                    typeof row.NUMBER,
                                keys:
                                    Object.keys(row)
                            }
                        );
                    }


                    // Check property existence

                    const hasIdPubs =
                        Object.prototype
                            .hasOwnProperty
                            .call(row, "IdPubs");

                    const hasNUMBER =
                        Object.prototype
                            .hasOwnProperty
                            .call(row, "NUMBER");


                    if (!hasIdPubs || !hasNUMBER) {

                        failed = true;

                        console.error(
                            "🚨 INVALID RECORD FOUND",
                            {
                                store: storeName,
                                index: index,
                                row: row,
                                hasIdPubs: hasIdPubs,
                                hasNUMBER: hasNUMBER,
                                IdPubs: row.IdPubs,
                                NUMBER: row.NUMBER,
                                keys: Object.keys(row)
                            }
                        );

                        transaction.abort();

                        reject(
                            new Error(
                                `RECORDS row ${index} is missing ` +
                                `${!hasIdPubs ? "IdPubs" : ""}` +
                                `${!hasNUMBER ? " NUMBER" : ""}`
                            )
                        );

                        return;
                    }


                    // Check undefined/null

                    if (
                        row.IdPubs === undefined ||
                        row.IdPubs === null ||
                        row.NUMBER === undefined ||
                        row.NUMBER === null
                    ) {

                        failed = true;

                        console.error(
                            "🚨 INVALID RECORD KEY",
                            {
                                index: index,
                                IdPubs: row.IdPubs,
                                NUMBER: row.NUMBER,
                                row: row
                            }
                        );

                        transaction.abort();

                        reject(
                            new Error(
                                `RECORDS row ${index} ` +
                                `has invalid IdPubs or NUMBER`
                            )
                        );

                        return;
                    }
                }


                // =========================================
                // PUT
                // =========================================

                try {

                    store.put(row);

                }
                catch (error) {

                    failed = true;

                    console.error(
                        "❌ PUT FAILED",
                        {
                            store: storeName,
                            index: index,
                            row: row,
                            error: error,
                            message: error.message
                        }
                    );

                    transaction.abort();

                    reject(
                        new Error(
                            `IndexedDB PUT failed in ` +
                            `${storeName}, row ${index}: ` +
                            error.message
                        )
                    );
                }

            });
        }
    });
}

// ============================================================
// RESTORE BACKUP FROM CLOUD
// ============================================================
async function handleRestoreFromCloud() {

    const passcode =
        localStorage.getItem("user_passcode");

    if (!passcode) {
        alert("Passcode missing. Please log in again.");
        return;
    }

    const confirmed = confirm(
        "Restore from Cloud?\n\n" +
        "Your current local data will be replaced " +
        "with the cloud backup."
    );

    if (!confirmed) return;

    const syncStatus =
        window.parent.document.getElementById("sync-status");

    try {

        // ====================================================
        // 1. SHOW RESTORING STATUS
        // ====================================================

        if (syncStatus) {
            syncStatus.style.display = "inline";
            syncStatus.textContent =
                "● Restoring...";
            syncStatus.style.color =
                "#ffc107";
        }

        console.log(
            "☁️ Starting cloud restore..."
        );

        console.log(
            "🔑 Passcode:",
            passcode
        );


        // ====================================================
        // 2. GET BACKUP FROM CLOUD
        // ====================================================

        const response = await fetch(
            `/api/backup-restore/${encodeURIComponent(passcode)}`
        );

        if (!response.ok) {

            const errorData =
                await response.json()
                    .catch(() => ({}));

            throw new Error(
                errorData.detail ||
                `Server error ${response.status}`
            );
        }

        const result =
            await response.json();

        console.log(
            "☁️ Cloud backup received."
        );

        console.log(
            "🕒 Backup timestamp:",
            result.updated_at
        );

        if (!result.payload) {
            throw new Error(
                "Cloud backup contains no payload."
            );
        }


        // ====================================================
        // 3. SAVE RESTORED DATA INTO INDEXEDDB
        // ====================================================

        if (syncStatus) {
            syncStatus.style.display = "inline";
            syncStatus.textContent =
                "● Saving restored data...";
            syncStatus.style.color =
                "#ffc107";
        }

        console.log(
            "📥 Saving cloud backup into IndexedDB..."
        );

        await saveAllTablesToIndexedDB(
            result.payload
        );

        console.log(
            "✅ Cloud backup restored to IndexedDB."
        );


        // ====================================================
        // 4. MARK DATA AS SAVED
        // ====================================================

        localStorage.setItem(
            "sync_unsaved",
            "false"
        );

        if (result.updated_at) {
            localStorage.setItem(
                "last_sync_timestamp",
                result.updated_at
            );
        }


        // ====================================================
        // 5. SHOW SUCCESS
        // ====================================================

        if (syncStatus) {
            syncStatus.style.display = "inline";
            syncStatus.textContent =
                "● Restore complete";
            syncStatus.style.color =
                "#28a745";
        }

        console.log(
            "🟢 Restore complete. Sync status marked as saved."
        );


        // ====================================================
        // 6. SMALL DELAY SO USER CAN SEE SUCCESS
        // ====================================================

        await new Promise(resolve =>
            setTimeout(resolve, 800)
        );


        // ====================================================
        // 7. REFRESH APPLICATION
        // ====================================================

        window.location.reload();

    }
    catch (error) {

        console.error(
            "❌ Cloud restore failed:",
            error
        );


        // ====================================================
        // 8. SHOW ERROR STATUS
        // ====================================================

        if (syncStatus) {
            syncStatus.style.display = "inline";
            syncStatus.textContent =
                "● Restore failed";
            syncStatus.style.color =
                "#dc3545";
        }

        alert(
            "Restore failed:\n\n" +
            error.message
        );
    }
}



async function handleExportBackup(event) {
    event?.stopPropagation();

    try {
        console.log("📦 Starting CRB backup export...");

        const db = await openIndexedDB();

        const storeNames = [
            "CongInfo",
            "GROUPS",
            "PUBLISHERS",
            "MonthlyRecords",
            "RECORDS"
        ];

        const transaction = db.transaction(
            storeNames,
            "readonly"
        );

        const backupData = {};

        await Promise.all(
            storeNames.map(storeName => {
                return new Promise((resolve, reject) => {

                    const store =
                        transaction.objectStore(storeName);

                    const request = store.getAll();

                    request.onsuccess = () => {
                        backupData[storeName] =
                            request.result || [];

                        console.log(
                            `📤 Exporting ${storeName}:`,
                            backupData[storeName].length,
                            "records"
                        );

                        resolve();
                    };

                    request.onerror = () => reject(request.error);
                });
            })
        );

        await new Promise((resolve, reject) => {
            transaction.oncomplete = resolve;
            transaction.onerror = () =>
                reject(transaction.error);
        });

        db.close();

        const jsonString = JSON.stringify(
            backupData,
            null,
            2
        );

        const today =
            new Date().toISOString().split("T")[0];

        const fileName =
            `Congregation_Backup_${today}.crb`;

        // SHOW SAVE AS DIALOG
        if ("showSaveFilePicker" in window) {

            const fileHandle =
                await window.showSaveFilePicker({
                    suggestedName: fileName,
                    types: [
                        {
                            description: "Congregation Backup",
                            accept: {
                                "application/json": [".crb"]
                            }
                        }
                    ]
                });

            const writable =
                await fileHandle.createWritable();

            await writable.write(jsonString);

            await writable.close();

            console.log(
                "✅ Backup saved successfully:",
                fileHandle.name
            );

            alert(
                "Backup successfully saved!\n\n" +
                "File: " + fileHandle.name
            );

        } else {

            // FALLBACK FOR UNSUPPORTED BROWSERS
            const blob = new Blob(
                [jsonString],
                {
                    type: "application/json"
                }
            );

            const url =
                URL.createObjectURL(blob);

            const link =
                document.createElement("a");

            link.href = url;
            link.download = fileName;

            document.body.appendChild(link);
            link.click();
            link.remove();

            URL.revokeObjectURL(url);

            alert(
                "Backup downloaded successfully.\n\n" +
                "File: " + fileName
            );
        }

    }
    catch (error) {

        // User pressed Cancel
        if (error.name === "AbortError") {
            console.log("⚠️ Backup save cancelled.");
            return;
        }

        console.error(
            "❌ CRB Export failed:",
            error
        );

        alert(
            "Failed to export backup.\n\n" +
            error.message
        );
    }
}


      // ----------------------------------------------------
        // 4. import from downloaded backup
        // ----------------------------------------------------

async function handleImportBackup(event) {
    event?.stopPropagation();

    const input = document.createElement("input");

    input.type = "file";
    input.accept = ".crb,application/json";

    input.onchange = async () => {
        const file = input.files[0];

        if (!file) return;

        console.log(
            "📂 Selected CRB:",
            file.name
        );

        try {
            // Read CRB file
            const text = await file.text();

            // Convert JSON text to object
            let backupData;

            try {
                backupData = JSON.parse(text);
            }
            catch (error) {
                throw new Error(
                    "The selected CRB file is not valid."
                );
            }

            // Required IndexedDB stores
            const storeNames = [
                "CongInfo",
                "GROUPS",
                "PUBLISHERS",
                "MonthlyRecords",
                "RECORDS"
            ];

            // Validate backup structure
            for (const storeName of storeNames) {

                if (!Object.prototype.hasOwnProperty.call(
                    backupData,
                    storeName
                )) {
                    throw new Error(
                        `Missing table: ${storeName}`
                    );
                }

                if (!Array.isArray(
                    backupData[storeName]
                )) {
                    throw new Error(
                        `${storeName} is not an array.`
                    );
                }
            }

            console.log(
                "✅ CRB structure validated."
            );

            // Show what will be imported
            const summary = storeNames.map(
                storeName =>
                    `${storeName}: ` +
                    `${backupData[storeName].length} records`
            );

            const confirmed = confirm(
                "IMPORT BACKUP\n\n" +
                "This will replace the existing " +
                "IndexedDB data.\n\n" +
                summary.join("\n") +
                "\n\nContinue?"
            );

            if (!confirmed) {
                console.log(
                    "⚠️ CRB import cancelled."
                );
                return;
            }

            // Replace all 5 IndexedDB stores
            console.log(
                "📥 Importing CRB into IndexedDB..."
            );

            await saveAllTablesToIndexedDB(
                backupData
            );

            console.log(
                "✅ CRB imported successfully."
            );

            alert(
                "Backup imported successfully!\n\n" +
                "The 5 IndexedDB tables have been " +
                "replaced with the backup."
            );

            // Reload application
            location.reload();

        }
        catch (error) {

            console.error(
                "❌ CRB import failed:",
                error
            );

            alert(
                "Backup import failed.\n\n" +
                error.message
            );
        }
    };

    // Open file picker
    input.click();
}

function setSyncUnsaved() {

    const syncStatus =
        window.parent.document.getElementById("sync-status");

    localStorage.setItem(
        "sync_unsaved",
        "true"
    );

    if (syncStatus) {
        syncStatus.textContent = "";
        syncStatus.style.display = "none";
    }

    localStorage.removeItem(
        "last_sync_timestamp"
    );
}


function setSyncSaved(timestamp = Date.now()) {
    const syncStatus =
        window.parent.document.getElementById("sync-status");

    if (syncStatus) {
        syncStatus.textContent = "";
        syncStatus.style.display = "none";
    }

    localStorage.setItem(
        "last_sync_timestamp",
        timestamp
    );
}
