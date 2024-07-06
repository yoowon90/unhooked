function deleteWishItem(wishItemId) 
{
  fetch("/delete-wishitem", {
    method: "POST",
    body: JSON.stringify({ wishItemId: wishItemId }),
  }).then((_res) => {
    window.location.href = "/my-wishlist";
  });
}

function deleteNote(noteId) 
{
  fetch("/delete-note", {
    method: "POST",
    body: JSON.stringify({ noteId: noteId }),
  }).then((_res) => {
    window.location.href = "/";
  });
}