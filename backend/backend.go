package main

import (
	"encoding/json"
	"io"
	"log"
	"net/http"
	"flag"

	datastore "./datastore"
	tokenauth "./google-token-auth"
)

var (
	// Set allowed domains here.
	authorized_domains = []string{
		"csumb.edu",
	}

	// Client-side client ID from your Google Developer Console
	// Same as in the front-end index.php
	authorized_client_ids = []string{
		"266670200080-to3o173goghk64b6a0t0i04o18nt2r3i.apps.googleusercontent.com",
	}

	admin_users = map[string]bool{
        "abiblarz@csumb.edu": true,
        "sislam@csumb.edu":   true,
		"gbruns@csumb.edu":   true,
		"cohunter@csumb.edu": true,
	}

	// When started via systemd, WorkingDirectory is set to one level above the public_html directory
	database_uri = "file:db.sqlite3?cache=shared&mode=rwc&_journal_mode=WAL"
)

type userWithEmail interface {
	GetEmail() string
}

type Env struct {
	ds datastore.IProofStore
}

func getAdmins(w http.ResponseWriter, req *http.Request) {
	type adminUsers struct {
		Admins []string
	}
	var admins adminUsers
	for adminEmail := range admin_users {
		admins.Admins = append(admins.Admins, adminEmail)
	}
	output, err := json.Marshal(admins)
	if err != nil {
		http.Error(w, "Error returning admin users.", 500)
		return
	}

	// Allow browsers and intermediaries to cache this response for up to a day (86400 seconds)
	w.Header().Set("Cache-Control", "public, max-age=86400")
	io.WriteString(w, string(output))
}

func (env *Env) saveProof(w http.ResponseWriter, req *http.Request) {
	var user userWithEmail
	user = req.Context().Value("tok").(userWithEmail)
	
	var submittedProof datastore.Proof

	// read the JSON-encoded value from the HTTP request and store it in submittedProof
	if err := json.NewDecoder(req.Body).Decode(&submittedProof); err != nil {
		log.Println(err)
		http.Error(w, err.Error(), 400)
		return
	}

	log.Printf("%+v", submittedProof)

	if len(submittedProof.ProofName) == 0 {
		http.Error(w, "Proof name is empty", 400)
		return
	}

	// Replace submitted email (if any) with the email from the token
	submittedProof.UserSubmitted = user.GetEmail()

	if err := env.ds.Store(submittedProof); err != nil {
		http.Error(w, err.Error(), 500)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	io.WriteString(w, `{"success": "true"}`)
}

func (env *Env) getProofs(w http.ResponseWriter, req *http.Request) {
	user := req.Context().Value("tok").(userWithEmail)

	if req.Method != "POST" || req.Body == nil {
		http.Error(w, "Request not accepted.", 400)
		return
	}

	// Accepted JSON fields must be defined here
	type getProofRequest struct {
		Selection string `json:"selection"`
	}

	var requestData getProofRequest

	decoder := json.NewDecoder(req.Body)

	if err := decoder.Decode(&requestData); err != nil {
		http.Error(w, "Unable to decode request body.", 400)
		return
	}

	log.Printf("%+v", requestData)

	if len(requestData.Selection) == 0 {
		http.Error(w, "Selection required", 400)
		return
	}

	log.Printf("USER: %q", user)

	var err error
	var proofs []datastore.Proof

	switch requestData.Selection {
	case "user":
		log.Println("user selection")
		err, proofs = env.ds.GetUserProofs(user)

	case "repo":
		log.Println("repo selection")
		err, proofs = env.ds.GetRepoProofs()

	case "completedrepo":
		log.Println("completedrepo selection")
		err, proofs = env.ds.GetUserCompletedProofs(user)
	
	case "downloadrepo":
		log.Println("downloadrepo selection")
		if !admin_users[user.GetEmail()] {
			http.Error(w, "Insufficient privileges", 403)
			return
		}
		err, proofs = env.ds.GetAllAttemptedRepoProofs()

	default:
		http.Error(w, "invalid selection", 400)
		return
	}

	if err != nil {
		http.Error(w, "Query error", 500)
		return
	}

	log.Printf("%+v", proofs)
	userProofsJSON, err := json.Marshal(proofs)
	if err != nil {
		http.Error(w, "json marshal error", 500)
		log.Print(err)
		return
	}

	io.WriteString(w, string(userProofsJSON))

	log.Printf("%q", user)
	log.Printf("%+v", req.URL.Query())
}

// This will delete all rows, but not reset the auto_increment id
func (env *Env) clearDatabase() {
	if err := env.ds.Empty(); err != nil {
		log.Fatal(err)
	}
}

func (env *Env) populateTestData() {
	err := env.ds.Store(datastore.Proof{
		EntryType: "proof",
		UserSubmitted: "gbruns@csumb.edu",
		ProofName: "Repository - Problem 2",
		ProofType: "prop",
		Premise: []string{"P", "P -> Q", "Q -> R", "R -> S", "S -> T", "T -> U", "V -> W", "W -> X", "X -> Y", "Y -> X"},
		Logic: []string{},
		Rules: []string{},
		ProofCompleted: "false",
		Conclusion: "Y",
		TimeSubmitted: "2019-04-29T01:45:44.452+0000",
		RepoProblem: "true",
	})

	if err != nil {
		log.Fatal(err)
	}
}

func main() {
	log.Println("Server initializing")

	ds, err := datastore.New(database_uri)
	if err != nil {
		log.Fatal(err)
	}
	defer ds.Close()

	// Add the admin users to the database for use in queries
	ds.UpdateAdmins(admin_users)
	
	Env := &Env{ds} // Put the instance into a struct to share between threads

	doClearDatabase := flag.Bool("cleardb", false, "Remove all proofs from the database")
	doPopulateDatabase := flag.Bool("populate", false, "Add sample data to the public repository.")
	portPtr := flag.String("port", "8080", "Port to listen on")

	flag.Parse() // Check for command-line arguments
	if *doClearDatabase {
		Env.clearDatabase()
	}
	if *doPopulateDatabase {
		Env.populateTestData()
	}

	// Initialize token auth/cache
	tokenauth.SetAuthorizedDomains(authorized_domains)
	tokenauth.SetAuthorizedClientIds(authorized_client_ids)

	// method saveproof : POST : JSON <- id_token, proof
	http.Handle("/saveproof", tokenauth.WithValidToken(http.HandlerFunc(Env.saveProof)))

	// method user : POST : JSON -> [proof, proof, ...]
	http.Handle("/proofs", tokenauth.WithValidToken(http.HandlerFunc(Env.getProofs)))

	// Get admin users -- this is a public endpoint, no token required
	// Can be changed to require token, but would reduce cacheability
	http.Handle("/admins", http.HandlerFunc(getAdmins))
	log.Println("Server started")
	log.Fatal(http.ListenAndServe("127.0.0.1:"+(*portPtr), nil))
}
